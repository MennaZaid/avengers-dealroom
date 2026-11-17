"""Database access that runs every request under a restricted Postgres role.

Read routes use `vos_app` (read-only on the registry); admin routes use `vos_admin`.
So even a bug in a read route cannot write to the registry: Postgres refuses it.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

import psycopg
from psycopg.rows import dict_row

from venture_os.config import Settings

Role = Literal["vos_app", "vos_admin", "vos_agent"]  # vos_agent: research agents (write evidence only)


@contextmanager
def connect(role: Role) -> Iterator[psycopg.Connection]:
    with psycopg.connect(Settings().database_url, row_factory=dict_row) as conn:
        conn.execute(f"SET ROLE {role}")  # role is a Literal, never user input
        yield conn
