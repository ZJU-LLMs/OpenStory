from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_map_character_art_uses_a_separate_overlay() -> None:
    html = (ROOT / "frontend" / "simulation.html").read_text(encoding="utf-8")

    canvas_index = html.index('id="mapCanvas"')
    overlay_index = html.index('id="mapAgentLayer"')
    assert canvas_index < overlay_index
    assert 'id="mapSurface"' in html


def test_map_character_overlay_is_redrawn_for_zoom_and_hidpi() -> None:
    script = (ROOT / "frontend" / "simulation-modern.js").read_text(encoding="utf-8")

    assert "function renderMapAgentLayer()" in script
    assert "window.devicePixelRatio" in script
    assert "spriteContext.setTransform(pixelRatio" in script
    assert "renderMapAgentLayer();" in script
    assert "mapSurface.style.width" in script
    assert "mapSurface.style.height" in script


def test_map_canvas_uses_a_hidpi_backing_store_with_world_coordinates() -> None:
    script = (ROOT / "frontend" / "simulation-modern.js").read_text(encoding="utf-8")

    assert "mapWorldWidth = grid.width * tilePx" in script
    assert "mapWorldHeight = grid.height * tilePx" in script
    assert "mapPixelRatio = Math.min(2" in script
    assert "canvas.width = backingWidth" in script
    assert "canvas.height = backingHeight" in script
    assert "ctx.setTransform(mapPixelRatio" in script
    assert "mapWorldWidth / rect.width" in script
    assert "mapWorldHeight / rect.height" in script


def test_map_uses_spawn_points_until_runtime_agents_are_available() -> None:
    script = (ROOT / "frontend" / "simulation-modern.js").read_text(encoding="utf-8")

    assert "function getDrawableMapAgents" in script
    assert "if (runtimeAgents.length) return runtimeAgents" in script
    assert "character_id: spawn.character_id" in script
    assert "position: spawn.position" in script


def test_location_labels_hide_when_the_map_is_zoomed_in() -> None:
    script = (ROOT / "frontend" / "simulation-modern.js").read_text(encoding="utf-8")

    assert "function shouldShowLocationLabels()" in script
    assert "return mapZoom <= 1.001" in script
    assert "if (!shouldShowLocationLabels()) return" in script
    assert "renderMap({ applyZoom: false })" in script
    assert "location-labels-hidden" in script


def test_map_character_overlay_does_not_intercept_map_input() -> None:
    stylesheet = (ROOT / "frontend" / "simulation-modern.css").read_text(encoding="utf-8")

    overlay_rule = stylesheet.split(".sim-page .map-agent-layer", 1)[1].split("}", 1)[0]
    assert "position: absolute" in overlay_rule
    assert "pointer-events: none" in overlay_rule


def test_map_event_content_uses_temporary_compact_markers() -> None:
    script = (ROOT / "frontend" / "simulation-modern.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "frontend" / "simulation-modern.css").read_text(encoding="utf-8")

    assert "EVENT_MARKER_VISIBLE_MS = 4500" in script
    assert "visibleEventMarkerIds" in script
    assert "showEventMarkers(events)" in script
    assert "hideEventMarkers()" in script
    assert "map-event-bubble" not in script
    assert ".map-event-marker" in stylesheet
    assert "width: 24px" in stylesheet
    assert 'url("assets/icon-chat.png")' in stylesheet


def test_map_character_sizing_grows_with_zoom_and_remains_edge_clamped() -> None:
    script = (ROOT / "frontend" / "simulation-modern.js").read_text(encoding="utf-8")

    assert "maxScreenHeight = selected ? 112 : 96" in script
    assert "maxScreenWidth = selected ? 84 : 72" in script
    assert "baseWorldHeight = tilePx * (selected ? 3.2 : 2.75)" in script
    assert "baseWorldHeight * displayScale" in script
    assert "const anchorX = clamp(rawAnchorX" in script
    assert "const anchorY = clamp(rawAnchorY" in script


def test_map_uses_the_full_book_page_and_tick_status_moves_to_navigation() -> None:
    html = (ROOT / "frontend" / "simulation.html").read_text(encoding="utf-8")
    stylesheet = (ROOT / "frontend" / "book-ui.css").read_text(encoding="utf-8")

    nav = html.split('<nav class="book-nav"', 1)[1].split("</nav>", 1)[0]
    controls = html.split('<div class="controls"', 1)[1].split("</div>", 1)[0]
    assert 'class="nav-tick-status"' in nav
    assert 'id="tickValue"' in nav
    assert 'id="tickBtn"' in controls
    assert 'id="autoBtn"' in controls
    assert 'id="stopBtn"' in controls
    assert 'class="map-heading"' not in html
    assert 'class="map-footer"' not in html
    assert ".nav-tick-status" in stylesheet
    assert "height: 100%" in stylesheet


def test_world_name_is_an_absolute_overlay_outside_the_map_layout() -> None:
    html = (ROOT / "frontend" / "simulation.html").read_text(encoding="utf-8")
    script = (ROOT / "frontend" / "simulation-modern.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "frontend" / "book-ui.css").read_text(encoding="utf-8")

    header = html.split('<header class="app-header">', 1)[1].split("</header>", 1)[0]
    world_panel = html.split('<section class="world-panel"', 1)[1].split("</section>", 1)[0]
    assert 'id="worldName"' in header
    assert 'id="worldName"' not in world_panel
    assert "function renderWorldName()" in script
    assert "worldBackground?.world_name" in script
    plaque_rule = stylesheet.split(".world-name-plaque", 1)[1].split("}", 1)[0]
    assert "position: absolute" in plaque_rule
    assert "pointer-events: none" in plaque_rule


def test_agents_wander_in_place_and_follow_route_centerlines_between_locations() -> None:
    script = (ROOT / "frontend" / "simulation-modern.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "frontend" / "simulation-modern.css").read_text(encoding="utf-8")

    queue_index = script.index("queueAgentMotions(runtime, nextRuntime)")
    runtime_update_index = script.index("runtime = nextRuntime", queue_index)
    assert queue_index < runtime_update_index
    assert "function buildRouteMotionPoints" in script
    assert "route.centerline" in script
    assert "from_location_id" in script
    assert "to_location_id" in script
    assert "sprite.animate(keyframes" in script
    assert "movementPlaybackUntil" not in script
    assert "existingMotionActive" in script
    assert ".slice(currentPoint.nextIndex)" in script
    assert "ROUTE_MOTION_MS_PER_TILE = 115" in script
    assert "ROUTE_MOTION_MAX_MS = 7600" in script
    assert "map-agent-wander" in stylesheet
    assert ".map-agent-sprite.moving" in stylesheet
    assert "map-agent-walk-bob" in stylesheet
    assert "@media (prefers-reduced-motion: reduce)" in stylesheet


def test_character_action_form_uses_task_assignment_wording() -> None:
    script = (ROOT / "frontend" / "simulation-modern.js").read_text(encoding="utf-8")

    assert '<div class="section-title">指派任务</div>' in script
    assert '<label>任务内容<textarea' in script
    assert 'placeholder="输入希望角色优先执行的任务"' in script
    assert '<button type="submit">指派任务</button>' in script
    assert "一次性下一行动" not in script
    assert "设为下一行动" not in script
