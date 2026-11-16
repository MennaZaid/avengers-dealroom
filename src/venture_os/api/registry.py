"""Registry API: sources, RAG corpus, technology components and model endpoints.

Read routes are open to the app. Admin routes need the X-Admin-Token header and log every change
with the admin's id and a reason. Nothing is ever deleted: "remove" deactivates.
"""

import hmac
import json
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from venture_os.api.db import connect
from venture_os.config import Settings

router = APIRouter(prefix="/registry", tags=["registry"])
admin = APIRouter(prefix="/admin", tags=["admin"])


# ---------- read routes ----------

@router.get("/sources")
def list_sources(
    country: str | None = Query(None, description="ISO 3166-1 alpha-2; also returns global sources"),
    tier: Literal["A", "B", "C"] | None = None,
    use: str | None = None,
    include_inactive: bool = False,
):
    where, args = [], {}
    if not include_inactive:
        where.append("active")
    if country:
        where.append("(country_codes = '{}' OR %(cc)s = ANY(country_codes))")
        args["cc"] = country.upper()
    if tier:
        where.append("tier = %(tier)s")
        args["tier"] = tier
    if use:
        where.append("use = %(use)s")
        args["use"] = use
    sql = "SELECT * FROM sources" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id"
    with connect("vos_app") as conn:
        return conn.execute(sql, args).fetchall()


@router.get("/sources/{source_id}")
def get_source(source_id: str):
    with connect("vos_app") as conn:
        row = conn.execute("SELECT * FROM sources WHERE id = %s", (source_id,)).fetchone()
    if not row:
        raise HTTPException(404, "source not found")
    return row


@router.get("/corpus")
def list_corpus(status: str | None = None):
    with connect("vos_app") as conn:
        if status:
            return conn.execute("SELECT * FROM corpus_items WHERE status = %s ORDER BY id", (status,)).fetchall()
        return conn.execute("SELECT * FROM corpus_items ORDER BY id").fetchall()


@router.get("/components")
def list_components(kind: str | None = None, status: str | None = None, include_inactive: bool = False):
    where, args = [], {}
    if not include_inactive:
        where.append("active")
    if kind:
        where.append("kind = %(kind)s")
        args["kind"] = kind
    if status:
        where.append("status = %(status)s")
        args["status"] = status
    sql = "SELECT * FROM components" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id"
    with connect("vos_app") as conn:
        return conn.execute(sql, args).fetchall()


@router.get("/endpoints")
def list_endpoints(profile: str | None = None):
    """Model endpoints in fallback order. Returns env var NAMES only, never secret values."""
    with connect("vos_app") as conn:
        if profile:
            return conn.execute(
                "SELECT * FROM model_endpoints WHERE active AND profile = %s ORDER BY priority", (profile,)
            ).fetchall()
        return conn.execute("SELECT * FROM model_endpoints WHERE active ORDER BY profile, priority").fetchall()


@router.get("/summary")
def summary():
    with connect("vos_app") as conn:
        return {
            "sources_by_tier": conn.execute(
                "SELECT tier, count(*) AS n FROM sources WHERE active GROUP BY tier ORDER BY tier"
            ).fetchall(),
            "provisional_sources": conn.execute(
                "SELECT count(*) AS n FROM sources WHERE active AND provisional"
            ).fetchone()["n"],
            "corpus_items": conn.execute("SELECT count(*) AS n FROM corpus_items").fetchone()["n"],
            "components_by_kind": conn.execute(
                "SELECT kind, count(*) AS n FROM components WHERE active GROUP BY kind ORDER BY kind"
            ).fetchall(),
            "endpoints": conn.execute("SELECT count(*) AS n FROM model_endpoints WHERE active").fetchone()["n"],
        }


# ---------- admin routes ----------

def require_admin(x_admin_token: str = Header(""), x_admin_id: str = Header("")) -> str:
    expected = Settings().admin_token
    if not expected:
        raise HTTPException(503, "admin routes disabled: ADMIN_TOKEN is not set")
    if not hmac.compare_digest(x_admin_token, expected):
        raise HTTPException(401, "invalid admin token")
    if not x_admin_id:
        raise HTTPException(400, "X-Admin-Id header required for the change log")
    return x_admin_id


class SourceIn(BaseModel):
    id: str = Field(pattern=r"^[A-Z]{1,3}-\d{3,}$")
    scope: Literal["global", "region", "country", "industry"]
    source_name: str
    url: str = Field(pattern=r"^https://")
    provides: str | None = None
    access_type: str | None = None
    license: str | None = None
    coverage: str | None = None
    country_codes: list[str] = []
    max_age_months: int | None = None
    tier: Literal["A", "B", "C"]
    crawl: Literal["full", "metadata", "none"] = "full"
    use: str = "market"
    notes: str | None = None
    reason: str = Field(min_length=5)


class ComponentIn(BaseModel):
    id: str = Field(pattern=r"^T-\d{3,}$")
    kind: str
    name: str
    url: str | None = None
    license: str | None = None
    open_weight: bool | None = None
    osi_open: bool | None = None
    use: str | None = None
    status: Literal["candidate", "selected", "rejected"] = "candidate"
    notes: str | None = None
    reason: str = Field(min_length=5)


class Reason(BaseModel):
    reason: str = Field(min_length=5)


def _insert(conn, table: str, row: dict) -> dict:
    cols = ", ".join(row)
    vals = ", ".join(f"%({k})s" for k in row)
    out = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({vals}) ON CONFLICT (id) DO NOTHING RETURNING *", row)
    created = out.fetchone()
    if not created:
        raise HTTPException(409, f"{row['id']} already exists")
    return created


@admin.post("/sources", status_code=201)
def add_source(body: SourceIn, admin_id: str = Depends(require_admin)):
    row = body.model_dump(exclude={"reason"}) | {"created_by": admin_id, "verified": True}
    with connect("vos_admin") as conn:
        created = _insert(conn, "sources", row)
        conn.execute(
            "INSERT INTO source_changes (source_id, action, admin_id, reason, after) VALUES (%s,'add',%s,%s,%s)",
            (body.id, admin_id, body.reason, json.dumps(created, default=str)),
        )
    return created


def _set_active(table: str, log: str, row_id: str, active: bool, admin_id: str, reason: str) -> dict:
    action = "reactivate" if active else "deactivate"
    with connect("vos_admin") as conn:
        before = conn.execute(f"SELECT * FROM {table} WHERE id = %s", (row_id,)).fetchone()
        if not before:
            raise HTTPException(404, f"{row_id} not found")
        extra = ", provisional = false, expires_at = NULL" if (table == "sources" and active) else ""
        after = conn.execute(
            f"UPDATE {table} SET active = %s, updated_at = now(){extra} WHERE id = %s RETURNING *", (active, row_id)
        ).fetchone()
        if log == "source_changes":
            conn.execute(
                "INSERT INTO source_changes (source_id, action, admin_id, reason, before, after)"
                " VALUES (%s,%s,%s,%s,%s,%s)",
                (row_id, action, admin_id, reason, json.dumps(before, default=str), json.dumps(after, default=str)),
            )
        else:
            conn.execute(
                "INSERT INTO catalog_changes (table_name, row_id, action, admin_id, reason, before, after)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (table, row_id, action, admin_id, reason,
                 json.dumps(before, default=str), json.dumps(after, default=str)),
            )
    return after


@admin.post("/sources/{source_id}/deactivate")
def deactivate_source(source_id: str, body: Reason, admin_id: str = Depends(require_admin)):
    return _set_active("sources", "source_changes", source_id, False, admin_id, body.reason)


@admin.post("/sources/{source_id}/confirm")
def confirm_source(source_id: str, body: Reason, admin_id: str = Depends(require_admin)):
    """Confirm a provisional source (or reactivate a deactivated one)."""
    with connect("vos_admin") as conn:
        before = conn.execute("SELECT * FROM sources WHERE id = %s", (source_id,)).fetchone()
        if not before:
            raise HTTPException(404, f"{source_id} not found")
        after = conn.execute(
            "UPDATE sources SET active = true, provisional = false, expires_at = NULL, verified = true,"
            " updated_at = now() WHERE id = %s RETURNING *",
            (source_id,),
        ).fetchone()
        conn.execute(
            "INSERT INTO source_changes (source_id, action, admin_id, reason, before, after)"
            " VALUES (%s,'confirm',%s,%s,%s,%s)",
            (source_id, admin_id, body.reason, json.dumps(before, default=str), json.dumps(after, default=str)),
        )
    return after


@admin.post("/components", status_code=201)
def add_component(body: ComponentIn, admin_id: str = Depends(require_admin)):
    row = body.model_dump(exclude={"reason"}) | {"created_by": admin_id}
    with connect("vos_admin") as conn:
        created = _insert(conn, "components", row)
        conn.execute(
            "INSERT INTO catalog_changes (table_name, row_id, action, admin_id, reason, after)"
            " VALUES ('components',%s,'add',%s,%s,%s)",
            (body.id, admin_id, body.reason, json.dumps(created, default=str)),
        )
    return created


@admin.post("/components/{component_id}/deactivate")
def deactivate_component(component_id: str, body: Reason, admin_id: str = Depends(require_admin)):
    return _set_active("components", "catalog_changes", component_id, False, admin_id, body.reason)


@admin.get("/changes")
def recent_changes(limit: int = Query(50, le=500), _: str = Depends(require_admin)):
    with connect("vos_admin") as conn:
        return {
            "sources": conn.execute(
                "SELECT * FROM source_changes ORDER BY id DESC LIMIT %s", (limit,)
            ).fetchall(),
            "catalog": conn.execute(
                "SELECT * FROM catalog_changes ORDER BY id DESC LIMIT %s", (limit,)
            ).fetchall(),
        }
