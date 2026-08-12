from __future__ import annotations

import json
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

from worldkernel.stage3.models import AgentKernelAdapterResult, InitialWorldPatch


def build_agentkernel_project(
    session_root: str | Path,
    output_dir: str | Path | None = None,
    max_ticks: int = 100,
) -> AgentKernelAdapterResult:
    """Sync completed WorldKernel outputs into the fixed Agent-Kernel runtime project."""

    session_root = Path(session_root).resolve()
    if not session_root.exists():
        raise FileNotFoundError(f"session root not found: {session_root}")

    patch = _load_initial_world_patch(session_root)
    project_root = _worldkernel_project_root()
    _ensure_runtime_data_dirs(project_root)

    transformed = _transform_patch(patch)
    _write_data(project_root, transformed)

    manifest = {
        "schema_version": "stage3-agentkernel-adapter-v1",
        "world_id": patch.world_id,
        "source_session_root": str(session_root),
        "counts": {
            "characters": len(transformed["profiles"]),
            "locations": len(transformed["locations"]),
            "paths": len(transformed["paths"]),
            "relations": len(transformed["relations"]),
            "spawn_points": len(transformed["agent_positions"]),
        },
        "warnings": patch.warnings + transformed["warnings"],
        "data_paths": {
            "agent_profiles": "data/agents/profiles.jsonl",
            "agent_states": "data/agents/states.jsonl",
            "agents_relation": "data/relations/relations.jsonl",
            "map_locations": "data/map/locations.json",
            "world_background": "data/world/background.json",
        },
    }
    manifest_path = project_root / "data" / "stage3_manifest.json"
    _write_json(manifest_path, manifest)

    dry_validation_passed, validation_warning = _dry_validate_project(project_root)
    warnings = list(manifest["warnings"])
    if output_dir is not None and Path(output_dir).resolve() != project_root:
        warnings.append("output_dir is ignored; WorldKernel uses the fixed examples/WorldKernel runtime project")
    if validation_warning:
        warnings.append(validation_warning)

    return AgentKernelAdapterResult(
        world_id=patch.world_id,
        project_root=str(project_root),
        entrypoint=str(project_root / "run_simulation.py"),
        manifest_path=str(manifest_path),
        counts=manifest["counts"],
        data_paths=manifest["data_paths"],
        warnings=warnings,
        dry_validation_passed=dry_validation_passed,
    )


def _load_initial_world_patch(session_root: Path) -> InitialWorldPatch:
    semantic_root, manifest_path = _find_semantic_root(session_root)
    manifest = _read_json(manifest_path)
    artifact_files = manifest.get("artifact_files", {})
    world_background = _load_world_background(session_root, manifest)

    locations = _read_artifact_items(semantic_root, artifact_files, "location_profile")
    characters = _read_artifact_items(semantic_root, artifact_files, "character_profile")
    paths = _read_artifact_items(semantic_root, artifact_files, "path_edge")
    relations = _read_artifact_items(semantic_root, artifact_files, "relation_edge")
    spatial = _read_json(_find_spatial_blueprint(session_root))

    warnings: list[str] = []
    for name, items in {
        "location_profile": locations,
        "character_profile": characters,
        "path_edge": paths,
        "relation_edge": relations,
    }.items():
        if not items:
            warnings.append(f"{name} artifact has no items")

    return InitialWorldPatch(
        world_id=manifest.get("world_id") or spatial.get("world_id") or session_root.name,
        world_background=world_background,
        characters=characters,
        locations=locations,
        paths=paths,
        relations=relations,
        spatial=spatial,
        provenance={"session_root": str(session_root), "semantic_manifest": str(manifest_path)},
        warnings=warnings,
    )


def _find_semantic_root(session_root: Path) -> tuple[Path, Path]:
    candidates = [
        session_root / "generated" / "artifacts" / "semantic" / "metadata" / "semantic_manifest.json",
        session_root / "generated" / "artifacts" / "metadata" / "semantic_manifest.json",
    ]
    for manifest_path in candidates:
        if manifest_path.exists():
            return manifest_path.parent.parent, manifest_path
    raise FileNotFoundError("Stage2 semantic_manifest.json not found; run Stage2 first")


def _find_spatial_blueprint(session_root: Path) -> Path:
    candidates = [
        session_root / "generated" / "artifacts" / "spatial" / "spatial_blueprint.json",
        session_root / "generated" / "stage2" / "spatial" / "spatial_blueprint.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("Stage2 spatial_blueprint.json not found; run spatial generation first")


def _load_world_background(session_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    candidates: list[Path] = []
    provenance = manifest.get("provenance", {}) if isinstance(manifest, dict) else {}
    stage1_inputs = provenance.get("stage1_inputs", {}) if isinstance(provenance, dict) else {}
    manifest_world_background = provenance.get("world_background", {}) if isinstance(provenance, dict) else {}

    for value in [
        stage1_inputs.get("world_background_path"),
        manifest_world_background.get("world_background_path"),
    ]:
        if value:
            path = Path(str(value))
            candidates.append(path if path.is_absolute() else session_root / path)

    candidates.extend(
        [
            session_root / "generated" / "plan" / "world_background.json",
            session_root / "generated" / "world_background.json",
        ]
    )
    for path in candidates:
        if path.exists():
            return _read_json(path)
    return {}


def _read_artifact_items(semantic_root: Path, artifact_files: dict[str, str], key: str) -> list[dict[str, Any]]:
    rel_path = artifact_files.get(key)
    if not rel_path:
        return []
    artifact = _read_json(semantic_root / rel_path)
    return artifact.get("items", [])


def _transform_patch(patch: InitialWorldPatch) -> dict[str, Any]:
    warnings: list[str] = []
    location_rows, location_id_to_name = _transform_locations(
        patch.locations, patch.spatial, warnings
    )
    # Stage3 reasons over semantic locations and their access rules. Route
    # topology and raster centerlines belong to the presentation client, which
    # reads the spatial blueprint directly.
    path_rows: list[dict[str, Any]] = []
    if patch.paths:
        warnings.append(
            "Stage3 omitted semantic path topology; frontend movement uses spatial blueprint routes"
        )
    profiles, states, agent_positions, character_id_to_agent = _transform_characters(
        patch.characters,
        patch.spatial,
        location_id_to_name,
        warnings,
    )
    relation_rows = _transform_relations(patch.relations, character_id_to_agent, warnings)
    return {
        "locations": location_rows,
        "paths": path_rows,
        "profiles": profiles,
        "states": states,
        "agent_positions": agent_positions,
        "relations": relation_rows,
        "world_background": patch.world_background,
        "warnings": warnings,
    }


def _transform_locations(
    raw_locations: list[dict[str, Any]],
    spatial: dict[str, Any],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    region_by_id = {r.get("location_id"): r for r in spatial.get("regions", []) if r.get("location_id")}
    rows: list[dict[str, Any]] = []
    id_to_name: dict[str, str] = {}

    for raw in raw_locations:
        identity = raw.get("identity", {})
        access = raw.get("access", {})
        state = raw.get("state", {})
        location_id = str(identity.get("id") or "")
        name = str(identity.get("name") or location_id)
        region = region_by_id.get(location_id, {})
        bounds = region.get("bounds") or {}
        entrance = region.get("entrance") or {}
        if not (
            region
            and isinstance(bounds, dict)
            and float(bounds.get("w", 0) or 0) > 0
            and float(bounds.get("h", 0) or 0) > 0
            and isinstance(entrance, dict)
            and "x" in entrance
            and "y" in entrance
        ):
            warnings.append(
                f"skipped semantic-only location {location_id or name!r}: not placed in spatial blueprint"
            )
            continue
        tags = [t for t in [identity.get("type"), access.get("access_level"), state.get("ownership")] if t]
        row = {
            "id": location_id,
            "name": name,
            "type": identity.get("type", ""),
            "description": identity.get("description", ""),
            "access": {
                "permissions": access.get("permissions", ""),
                "access_level": access.get("access_level", "open"),
                "access_conditions": access.get("access_conditions", ""),
                "access_scope": access.get("access_scope", ""),
                "gender_restriction": access.get("gender_restriction", ""),
                "time_restriction": access.get("time_restriction", ""),
                "special_event_access": access.get("special_event_access", ""),
            },
            "state": {
                "current_state": state.get("current_state", ""),
                "ownership": state.get("ownership", ""),
                "capacity": state.get("capacity", 0) or 0,
                "seasonal_state": state.get("seasonal_state", ""),
                "maintenance_condition": state.get("maintenance_condition", ""),
                "function_changed": state.get("function_changed", ""),
                "current_resident": state.get("current_resident", ""),
            },
            "capacity": state.get("capacity", 0) or 0,
            "tags": tags,
            "symbolic_meaning": identity.get("symbolic_meaning", ""),
            "key_plot_events": identity.get("key_plot_events", ""),
            "literary_imagery": identity.get("literary_imagery", ""),
            "raw": raw,
        }
        rows.append(row)
        if location_id:
            id_to_name[location_id] = name

    return rows, id_to_name


def _transform_paths(
    raw_paths: list[dict[str, Any]],
    spatial: dict[str, Any],
    location_id_to_name: dict[str, str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    route_by_id = {r.get("path_edge_id"): r for r in spatial.get("routes", []) if r.get("path_edge_id")}
    rows: list[dict[str, Any]] = []
    for raw in raw_paths:
        identity = raw.get("identity", {})
        endpoints = raw.get("endpoints", {})
        conditions = raw.get("conditions", {})
        path_id = str(identity.get("id") or "")
        from_id = str(endpoints.get("from_id") or "")
        to_id = str(endpoints.get("to_id") or "")
        if from_id not in location_id_to_name or to_id not in location_id_to_name:
            warnings.append(f"skipped path {path_id}: endpoint not found")
            continue
        route = route_by_id.get(path_id, {})
        if not route or not route.get("centerline"):
            warnings.append(f"skipped semantic-only path {path_id}: not rasterized in spatial blueprint")
            continue
        rows.append(
            {
                "id": path_id,
                "name": identity.get("name", ""),
                "type": identity.get("type", ""),
                "from_location_id": from_id,
                "to_location_id": to_id,
                "from_location": location_id_to_name[from_id],
                "to_location": location_id_to_name[to_id],
                "bidirectional": bool(endpoints.get("bidirectional", True)),
                "access_level": conditions.get("access_level", "open"),
                "danger_level": conditions.get("danger_level", ""),
                "required_items": conditions.get("required_items", ""),
                "gender_rule": conditions.get("gender_rule", ""),
                "traffic_restriction": endpoints.get("traffic_restriction", ""),
                "centerline": route.get("centerline", []),
                "movement_cost": route.get("movement_cost", 1.0),
                "access_tags": route.get("access_tags", []),
                "raw": raw,
            }
        )
    return rows


def _transform_characters(
    raw_characters: list[dict[str, Any]],
    spatial: dict[str, Any],
    location_id_to_name: dict[str, str],
    warnings: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, str]]:
    spawn_by_character = {
        sp.get("character_id"): sp for sp in spatial.get("spawn_points", []) if sp.get("character_id")
    }
    first_location_id = next(iter(location_id_to_name), "")
    used_agent_ids: dict[str, int] = {}
    character_id_to_agent: dict[str, str] = {}
    profiles: list[dict[str, Any]] = []
    states: list[dict[str, Any]] = []
    agent_positions: list[dict[str, Any]] = []

    for raw in raw_characters:
        identity = raw.get("identity", {})
        goals = raw.get("goals", {})
        memories = raw.get("memories", {})
        state = raw.get("state", {})
        personality = raw.get("personality", {}) or {}
        social_profile = raw.get("social_profile", {}) or {}
        capabilities = raw.get("capabilities", {}) or {}
        wk_id = str(identity.get("id") or "")
        base_agent_id = str(identity.get("name") or wk_id or f"agent_{len(profiles) + 1}")
        agent_id = _unique_agent_id(base_agent_id, used_agent_ids)
        character_id_to_agent[wk_id] = agent_id

        raw_location_id = _extract_character_location_id(raw)
        spawn = spawn_by_character.get(wk_id, {})
        location_id = str(spawn.get("location_id") or raw_location_id or first_location_id)
        if location_id not in location_id_to_name:
            warnings.append(f"agent {agent_id}: location {location_id!r} not found; using fallback")
            location_id = first_location_id
        current_location = location_id_to_name.get(location_id, "")
        position = spawn.get("position") or _extract_position(state) or [0, 0]

        profile = {
            "id": agent_id,
            "name": identity.get("name", agent_id),
            "role": identity.get("role", ""),
            "wk_entity_id": wk_id,
            "identity": identity,
            "tags": _coerce_string_list(identity.get("tags", [])),
            "personality": personality,
            "speech_style": personality.get("speech_style", ""),
            "values": personality.get("values", []),
            "capabilities": capabilities,
            "social_profile": social_profile,
            "long_term_goal": goals.get("long_term_goal", ""),
            "goals": {
                "long_term_goal": goals.get("long_term_goal", ""),
                "motivation": goals.get("motivation", ""),
            },
            "raw": raw,
        }
        profiles.append(profile)
        states.append(
            {
                "id": agent_id,
                "current_tick": 0,
                "is_active": True,
                "inactive_reason": "",
                "long_task": goals.get("long_term_goal") or None,
                "active_goal": goals.get("short_term_goal") or goals.get("active_goal") or None,
                "mood": state.get("mood") or state.get("emotional_state") or "",
                "status": state.get("status") or state.get("current_status") or "",
                "hourly_plans": {},
                "current_plan": None,
                "current_plan_note": None,
                "current_action": None,
                "occupied_by": None,
                "pending_user_action": None,
                "replanned_tick": None,
                "short_term_memory": {},
                "long_term_memory": [
                    {"tick": 0, "content": item}
                    for item in _coerce_string_list(memories.get("key_events", []))
                ],
                "dialogues": {},
                "event_log": {},
                "replan_log": [],
                "long_task_adj_log": [],
                "location_id": location_id,
                "current_location": current_location,
                # Pixel/grid position is presentation-only. The frontend gets
                # spawn anchors and route geometry from the spatial blueprint.
                "position": None,
                "memory": {
                    "background_summary": memories.get("background_summary", ""),
                    "key_events": _coerce_string_list(memories.get("key_events", [])),
                    "past_events": _coerce_string_list(memories.get("past_events", [])),
                    "recent_events": _coerce_string_list(memories.get("recent_events", [])),
                    "raw": memories,
                },
                "raw_state": state,
            }
        )
        agent_positions.append(
            {
                "id": agent_id,
                "wk_entity_id": wk_id,
                "location_id": location_id,
                "location": current_location,
                "position": position,
            }
        )

    return profiles, states, agent_positions, character_id_to_agent


def _transform_relations(
    raw_relations: list[dict[str, Any]],
    character_id_to_agent: dict[str, str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in raw_relations:
        edge = raw.get("edge", {})
        props = raw.get("properties", {})
        source = character_id_to_agent.get(str(edge.get("from_id") or ""))
        target = character_id_to_agent.get(str(edge.get("to_id") or ""))
        if not source or not target:
            warnings.append(f"skipped relation {edge.get('id', '')}: endpoint not found")
            continue
        relation = edge.get("kinship_type") or edge.get("love_type") or edge.get("type") or "related"
        rows.append(
            {
                "source": source,
                "target": target,
                "relation": relation,
                "strength": props.get("strength", ""),
                "description": props.get("description", ""),
                "properties": props,
                "raw": raw,
            }
        )
    return rows


def _extract_character_location_id(raw: dict[str, Any]) -> str:
    state = raw.get("state", {})
    location = state.get("location", {})
    if isinstance(location, dict):
        return str(location.get("location_id") or "")
    return ""


def _extract_position(state: dict[str, Any]) -> list[int] | None:
    position = state.get("position", {})
    if not isinstance(position, dict):
        return None
    try:
        return [int(float(position.get("x", 0))), int(float(position.get("y", 0)))]
    except (TypeError, ValueError):
        return None


def _unique_agent_id(base: str, used: dict[str, int]) -> str:
    normalized = base.strip() or "agent"
    used[normalized] = used.get(normalized, 0) + 1
    if used[normalized] == 1:
        return normalized
    return f"{normalized}__{used[normalized]}"


def _coerce_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if v]
    if value:
        return [str(value)]
    return []


def _worldkernel_project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _ensure_runtime_data_dirs(project_root: Path) -> None:
    for rel in [
        "data/agents",
        "data/relations",
        "data/map",
        "data/world",
    ]:
        (project_root / rel).mkdir(parents=True, exist_ok=True)


def _write_data(project_root: Path, transformed: dict[str, Any]) -> None:
    _write_jsonl(project_root / "data" / "agents" / "profiles.jsonl", transformed["profiles"])
    _write_jsonl(project_root / "data" / "agents" / "states.jsonl", transformed["states"])
    _write_jsonl(project_root / "data" / "relations" / "relations.jsonl", transformed["relations"])
    _write_jsonl(project_root / "data" / "map" / "agents.jsonl", transformed["agent_positions"])
    _write_json(project_root / "data" / "map" / "locations.json", transformed["locations"])
    _write_json(project_root / "data" / "map" / "paths.json", transformed["paths"])
    _write_json(project_root / "data" / "world" / "background.json", transformed["world_background"])


def _dry_validate_project(project_root: Path) -> tuple[bool, str | None]:
    try:
        _ensure_agentkernel_paths(project_root)
        from agentkernel_distributed.mas.builder import load_config

        load_config(str(project_root))
        return True, None
    except Exception as exc:
        return False, f"Agent-Kernel config dry validation failed: {exc}"


def _ensure_agentkernel_paths(project_root: Path) -> None:
    _ensure_optional_dependency_stubs()
    adapter_path = Path(__file__).resolve()
    for base in [project_root, *project_root.parents, adapter_path, *adapter_path.parents]:
        packages_root = base / "packages"
        if packages_root.exists():
            for child in packages_root.iterdir():
                if child.is_dir():
                    child_str = str(child)
                    if child_str not in sys.path:
                        sys.path.insert(0, child_str)
            break


def _ensure_optional_dependency_stubs() -> None:
    if "faker" not in sys.modules and importlib.util.find_spec("faker") is None:
        faker_stub = types.ModuleType("faker")

        class Faker:  # pragma: no cover - only used when optional dependency is absent
            pass

        faker_stub.Faker = Faker
        sys.modules["faker"] = faker_stub
    if "redis" not in sys.modules and importlib.util.find_spec("redis") is None:
        redis_stub = types.ModuleType("redis")
        redis_asyncio_stub = types.ModuleType("redis.asyncio")

        class ConnectionPool:  # pragma: no cover
            @classmethod
            def from_url(cls, *args: Any, **kwargs: Any):
                return cls()

            async def disconnect(self) -> None:
                return None

        class StrictRedis:  # pragma: no cover
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def ping(self) -> bool:
                return True

            async def close(self) -> None:
                return None

        redis_asyncio_stub.ConnectionPool = ConnectionPool
        redis_asyncio_stub.StrictRedis = StrictRedis
        redis_asyncio_stub.Redis = StrictRedis
        redis_stub.asyncio = redis_asyncio_stub
        sys.modules["redis"] = redis_stub
        sys.modules["redis.asyncio"] = redis_asyncio_stub
    if "pymilvus" not in sys.modules and importlib.util.find_spec("pymilvus") is None:
        pymilvus_stub = types.ModuleType("pymilvus")

        class AsyncMilvusClient:  # pragma: no cover
            pass

        class CollectionSchema:  # pragma: no cover
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

        class FieldSchema:  # pragma: no cover
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

        class DataType:  # pragma: no cover
            VARCHAR = "VARCHAR"
            FLOAT_VECTOR = "FLOAT_VECTOR"
            DOUBLE = "DOUBLE"
            INT64 = "INT64"

        pymilvus_stub.AsyncMilvusClient = AsyncMilvusClient
        pymilvus_stub.CollectionSchema = CollectionSchema
        pymilvus_stub.FieldSchema = FieldSchema
        pymilvus_stub.DataType = DataType
        sys.modules["pymilvus"] = pymilvus_stub
    if "asyncpg" not in sys.modules and importlib.util.find_spec("asyncpg") is None:
        asyncpg_stub = types.ModuleType("asyncpg")

        class Pool:  # pragma: no cover
            pass

        class Connection:  # pragma: no cover
            pass

        async def create_pool(*args: Any, **kwargs: Any) -> Pool:  # pragma: no cover
            return Pool()

        pool_stub = types.ModuleType("asyncpg.pool")
        pool_stub.Pool = Pool
        pool_stub.PoolAcquireContext = type("PoolAcquireContext", (), {})
        asyncpg_stub.Pool = Pool
        asyncpg_stub.Connection = Connection
        asyncpg_stub.create_pool = create_pool
        asyncpg_stub.pool = pool_stub
        sys.modules["asyncpg"] = asyncpg_stub
        sys.modules["asyncpg.pool"] = pool_stub
    if "fastmcp" not in sys.modules and importlib.util.find_spec("fastmcp") is None:
        fastmcp_stub = types.ModuleType("fastmcp")

        class Client:  # pragma: no cover
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> "Client":
                return self

            async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
                return None

            async def list_tools(self) -> list[Any]:
                return []

            async def call_tool(self, *args: Any, **kwargs: Any) -> Any:
                return None

        fastmcp_stub.Client = Client
        sys.modules["fastmcp"] = fastmcp_stub
    if "ray" not in sys.modules and importlib.util.find_spec("ray") is None:
        ray_stub = types.ModuleType("ray")
        actor_stub = types.ModuleType("ray.actor")

        class ActorHandle:  # pragma: no cover
            pass

        def remote(*args: Any, **kwargs: Any) -> Any:  # pragma: no cover
            if args and callable(args[0]) and len(args) == 1 and not kwargs:
                return args[0]

            def decorator(target: Any) -> Any:
                return target

            return decorator

        ray_stub.remote = remote
        ray_stub.is_initialized = lambda: False
        ray_stub.init = lambda *args, **kwargs: None
        ray_stub.shutdown = lambda: None
        ray_stub.get_actor = lambda *args, **kwargs: None
        ray_stub.kill = lambda *args, **kwargs: None
        ray_stub.get = lambda value: value
        ray_stub.put = lambda value: value
        actor_stub.ActorHandle = ActorHandle
        ray_stub.actor = actor_stub
        sys.modules["ray"] = ray_stub
        sys.modules["ray.actor"] = actor_stub
    if "fastapi" not in sys.modules and importlib.util.find_spec("fastapi") is None:
        fastapi_stub = types.ModuleType("fastapi")
        responses_stub = types.ModuleType("fastapi.responses")
        cors_stub = types.ModuleType("fastapi.middleware.cors")
        middleware_stub = types.ModuleType("fastapi.middleware")
        staticfiles_stub = types.ModuleType("fastapi.staticfiles")

        class FastAPI:  # pragma: no cover
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

            def add_middleware(self, *args: Any, **kwargs: Any) -> None:
                return None

            def mount(self, *args: Any, **kwargs: Any) -> None:
                return None

            def get(self, *args: Any, **kwargs: Any) -> Any:
                return lambda func: func

            def post(self, *args: Any, **kwargs: Any) -> Any:
                return lambda func: func

            def websocket(self, *args: Any, **kwargs: Any) -> Any:
                return lambda func: func

        class HTTPException(Exception):  # pragma: no cover
            def __init__(self, status_code: int = 500, detail: str | None = None) -> None:
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        class WebSocket:  # pragma: no cover
            pass

        class WebSocketDisconnect(Exception):  # pragma: no cover
            pass

        class Request:  # pragma: no cover
            pass

        class Response:  # pragma: no cover
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

        class JSONResponse(Response):  # pragma: no cover
            pass

        class CORSMiddleware:  # pragma: no cover
            pass

        class StaticFiles:  # pragma: no cover
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                pass

        fastapi_stub.FastAPI = FastAPI
        fastapi_stub.HTTPException = HTTPException
        fastapi_stub.WebSocket = WebSocket
        fastapi_stub.WebSocketDisconnect = WebSocketDisconnect
        fastapi_stub.Request = Request
        responses_stub.Response = Response
        responses_stub.JSONResponse = JSONResponse
        cors_stub.CORSMiddleware = CORSMiddleware
        staticfiles_stub.StaticFiles = StaticFiles
        sys.modules["fastapi"] = fastapi_stub
        sys.modules["fastapi.responses"] = responses_stub
        sys.modules["fastapi.middleware"] = middleware_stub
        sys.modules["fastapi.middleware.cors"] = cors_stub
        sys.modules["fastapi.staticfiles"] = staticfiles_stub
    if "uvicorn" not in sys.modules and importlib.util.find_spec("uvicorn") is None:
        uvicorn_stub = types.ModuleType("uvicorn")
        uvicorn_stub.run = lambda *args, **kwargs: None
        sys.modules["uvicorn"] = uvicorn_stub


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    content = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                json.loads(line)


