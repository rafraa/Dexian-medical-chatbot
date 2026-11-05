import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _timestamp() -> str:
	return datetime.now(timezone.utc).isoformat()


class ConversationStore:
	"""Persist local chat threads and their bounded-context summary state."""

	def __init__(self, db_path: str | Path) -> None:
		self.db_path = Path(db_path)
		self.db_path.parent.mkdir(parents=True, exist_ok=True)
		with closing(sqlite3.connect(self.db_path, timeout=10)) as connection:
			connection.execute("PRAGMA foreign_keys = ON")
			connection.executescript(
				"""
				CREATE TABLE IF NOT EXISTS conversations (
					id TEXT PRIMARY KEY,
					title TEXT NOT NULL,
					created_at TEXT NOT NULL,
					updated_at TEXT NOT NULL,
					context_summary TEXT NOT NULL DEFAULT '',
					summarized_through_message_id INTEGER NOT NULL DEFAULT 0
				);
				CREATE TABLE IF NOT EXISTS messages (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					conversation_id TEXT NOT NULL,
					role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
					content TEXT NOT NULL,
					sources_json TEXT NOT NULL DEFAULT '[]',
					sources_visible INTEGER NOT NULL DEFAULT 0,
					created_at TEXT NOT NULL,
					FOREIGN KEY (conversation_id) REFERENCES conversations(id)
						ON DELETE CASCADE
				);
				CREATE INDEX IF NOT EXISTS messages_conversation_id_id
					ON messages(conversation_id, id);
				"""
			)
			connection.commit()

	def _connect(self) -> sqlite3.Connection:
		connection = sqlite3.connect(self.db_path, timeout=10)
		connection.row_factory = sqlite3.Row
		connection.execute("PRAGMA foreign_keys = ON")
		return connection

	def create_conversation(self, title: str = "New chat") -> dict[str, str]:
		conversation_id = str(uuid4())
		now = _timestamp()
		with closing(self._connect()) as connection, connection:
			connection.execute(
				"""
				INSERT INTO conversations (id, title, created_at, updated_at)
				VALUES (?, ?, ?, ?)
				""",
				(conversation_id, title.strip() or "New chat", now, now),
			)
		return {
			"id": conversation_id,
			"title": title.strip() or "New chat",
			"created_at": now,
			"updated_at": now,
		}

	def list_conversations(self) -> list[dict[str, str]]:
		with closing(self._connect()) as connection:
			rows = connection.execute(
				"""
				SELECT id, title, created_at, updated_at
				FROM conversations
				ORDER BY updated_at DESC, id DESC
				"""
			).fetchall()
		return [dict(row) for row in rows]

	def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
		with closing(self._connect()) as connection:
			conversation = connection.execute(
				"""
				SELECT id, title, created_at, updated_at, context_summary,
					summarized_through_message_id
				FROM conversations WHERE id = ?
				""",
				(conversation_id,),
			).fetchone()
			if conversation is None:
				return None
			messages = connection.execute(
				"""
				SELECT id, role, content, sources_json, sources_visible, created_at
				FROM messages WHERE conversation_id = ? ORDER BY id
				""",
				(conversation_id,),
			).fetchall()

		return {
			**dict(conversation),
			"messages": [self._message_from_row(row) for row in messages],
		}

	def get_context_state(self, conversation_id: str) -> dict[str, Any] | None:
		with closing(self._connect()) as connection:
			conversation = connection.execute(
				"""
				SELECT context_summary, summarized_through_message_id
				FROM conversations WHERE id = ?
				""",
				(conversation_id,),
			).fetchone()
			if conversation is None:
				return None
			messages = connection.execute(
				"""
				SELECT id, role, content FROM messages
				WHERE conversation_id = ? ORDER BY id
				""",
				(conversation_id,),
			).fetchall()
		return {
			"summary": conversation["context_summary"],
			"summarized_through_message_id": conversation[
				"summarized_through_message_id"
			],
			"messages": [dict(row) for row in messages],
		}

	def append_exchange(
		self,
		conversation_id: str,
		question: str,
		answer: str,
		sources: list[dict[str, Any]],
		sources_visible: bool,
		context_summary: str,
		summarized_through_message_id: int,
	) -> dict[str, dict[str, Any]]:
		now = _timestamp()
		encoded_sources = json.dumps(sources, ensure_ascii=False)
		with closing(self._connect()) as connection, connection:
			conversation = connection.execute(
				"SELECT title FROM conversations WHERE id = ?",
				(conversation_id,),
			).fetchone()
			if conversation is None:
				raise KeyError(conversation_id)

			user_cursor = connection.execute(
				"""
				INSERT INTO messages
					(conversation_id, role, content, created_at)
				VALUES (?, 'user', ?, ?)
				""",
				(conversation_id, question, now),
			)
			assistant_cursor = connection.execute(
				"""
				INSERT INTO messages
					(conversation_id, role, content, sources_json, sources_visible, created_at)
				VALUES (?, 'assistant', ?, ?, ?, ?)
				""",
				(
					conversation_id,
					answer,
					encoded_sources,
					int(sources_visible),
					now,
				),
			)
			title = conversation["title"]
			if title == "New chat":
				title = " ".join(question.split())[:72].strip() or "New chat"
				if len(" ".join(question.split())) > 72:
					title = f"{title.rstrip()}…"
			connection.execute(
				"""
				UPDATE conversations
				SET title = ?, updated_at = ?, context_summary = ?,
					summarized_through_message_id = ?
				WHERE id = ?
				""",
				(
					title,
					now,
					context_summary,
					summarized_through_message_id,
					conversation_id,
				),
			)

		return {
			"user_message": {
				"id": user_cursor.lastrowid,
				"role": "user",
				"content": question,
				"sources": [],
				"sources_visible": False,
				"created_at": now,
			},
			"assistant_message": {
				"id": assistant_cursor.lastrowid,
				"role": "assistant",
				"content": answer,
				"sources": sources,
				"sources_visible": sources_visible,
				"created_at": now,
			},
		}

	def replace_exchange(
		self,
		conversation_id: str,
		message_id: int,
		question: str,
		answer: str,
		sources: list[dict[str, Any]],
		sources_visible: bool,
		context_summary: str,
		summarized_through_message_id: int,
	) -> dict[str, dict[str, Any]]:
		now = _timestamp()
		encoded_sources = json.dumps(sources, ensure_ascii=False)
		with closing(self._connect()) as connection, connection:
			conversation = connection.execute(
				"SELECT title FROM conversations WHERE id = ?",
				(conversation_id,),
			).fetchone()
			target = connection.execute(
				"""
				SELECT role, created_at FROM messages
				WHERE id = ? AND conversation_id = ?
				""",
				(message_id, conversation_id),
			).fetchone()
			if conversation is None or target is None or target["role"] != "user":
				raise KeyError(message_id)

			connection.execute(
				"DELETE FROM messages WHERE conversation_id = ? AND id > ?",
				(conversation_id, message_id),
			)
			connection.execute(
				"""
				UPDATE messages
				SET content = ?, sources_json = '[]', sources_visible = 0
				WHERE id = ? AND conversation_id = ?
				""",
				(question, message_id, conversation_id),
			)
			assistant_cursor = connection.execute(
				"""
				INSERT INTO messages
					(conversation_id, role, content, sources_json, sources_visible, created_at)
				VALUES (?, 'assistant', ?, ?, ?, ?)
				""",
				(
					conversation_id,
					answer,
					encoded_sources,
					int(sources_visible),
					now,
				),
			)
			title = conversation["title"]
			if message_id == connection.execute(
				"""
				SELECT MIN(id) FROM messages WHERE conversation_id = ?
				""",
				(conversation_id,),
			).fetchone()[0]:
				title = " ".join(question.split())[:72].strip() or "New chat"
				if len(" ".join(question.split())) > 72:
					title = f"{title.rstrip()}…"
			connection.execute(
				"""
				UPDATE conversations
				SET title = ?, updated_at = ?, context_summary = ?,
					summarized_through_message_id = ?
				WHERE id = ?
				""",
				(
					title,
					now,
					context_summary,
					summarized_through_message_id,
					conversation_id,
				),
			)

		return {
			"user_message": {
				"id": message_id,
				"role": "user",
				"content": question,
				"sources": [],
				"sources_visible": False,
				"created_at": target["created_at"],
			},
			"assistant_message": {
				"id": assistant_cursor.lastrowid,
				"role": "assistant",
				"content": answer,
				"sources": sources,
				"sources_visible": sources_visible,
				"created_at": now,
			},
		}

	def delete_conversation(self, conversation_id: str) -> bool:
		with closing(self._connect()) as connection, connection:
			cursor = connection.execute(
				"DELETE FROM conversations WHERE id = ?",
				(conversation_id,),
			)
		return cursor.rowcount > 0

	@staticmethod
	def _message_from_row(row: sqlite3.Row) -> dict[str, Any]:
		return {
			"id": row["id"],
			"role": row["role"],
			"content": row["content"],
			"sources": json.loads(row["sources_json"])
			if row["sources_visible"]
			else [],
			"sources_visible": bool(row["sources_visible"]),
			"created_at": row["created_at"],
		}
