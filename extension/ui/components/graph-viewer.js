import * as THREE from "/ui/vendor/three.module.js";

const state = {
  renderer: null,
  scene: null,
  camera: null,
  group: null,
  raycaster: new THREE.Raycaster(),
  pointer: new THREE.Vector2(),
  nodeMeshes: [],
  nodeById: new Map(),
  nodeRecords: [],
  selectedMesh: null,
  selectedMarker: null,
  selectedLabel: null,
  selectedNodeId: "",
  dragging: false,
  moved: false,
  lastX: 0,
  lastY: 0,
  mode: "orbit",
  graphRadius: 8,
  overviewZoom: 16,
  maxZoom: 30,
  animationId: null,
};

const palette = {
  Class: 0x0b5cff,
  Function: 0x059669,
  Method: 0x0aa1ff,
  Test: 0x7c3aed,
  File: 0xf59e0b,
  Other: 0xd29922,
};

function $(id) {
  return document.getElementById(id);
}

function escapeHtml(text) {
  if (window.escapeHtml) return window.escapeHtml(text);
  return String(text || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function colorForNode(node) {
  if (node.is_test || node.kind === "Test") return palette.Test;
  return palette[node.kind] || palette.Other;
}

function cssColorForNode(node) {
  return `#${colorForNode(node).toString(16).padStart(6, "0")}`;
}

function radiusForNode(node) {
  const overviewScale = Math.max(0.026, state.graphRadius * 0.0046);
  const degreeBoost = Math.sqrt(node.degree || 0) * overviewScale * 0.045;
  return Math.max(overviewScale, Math.min(overviewScale * 1.45, overviewScale + degreeBoost));
}

function ensureEnhancements() {
  const stage = $("graphCanvas3d")?.parentElement;
  if (!stage || stage.querySelector(".kg-toolbar")) return;

  const toolbar = document.createElement("div");
  toolbar.className = "kg-toolbar";
  toolbar.innerHTML = `
    <button class="kg-tool active" data-mode="orbit" type="button">Orbit</button>
    <button class="kg-tool" data-mode="focus" type="button">Focus</button>
    <button class="kg-tool" data-action="reset" type="button">Reset</button>
  `;
  toolbar.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.dataset.mode) {
      state.mode = button.dataset.mode;
      toolbar.querySelectorAll(".kg-tool").forEach((el) => {
        el.classList.toggle("active", el.dataset.mode === state.mode);
      });
    }
    if (button.dataset.action === "reset") resetCamera();
  });
  stage.appendChild(toolbar);

  const watermark = document.createElement("div");
  watermark.className = "kg-watermark";
  watermark.textContent = "3D Code Knowledge Graph";
  stage.appendChild(watermark);
}

function makeLabelSprite(text, selected = false) {
  const label = String(text || "node").slice(0, 30);
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  const fontSize = selected ? 30 : 20;
  ctx.font = `800 ${fontSize}px Inter, Arial, sans-serif`;
  const width = Math.ceil(ctx.measureText(label).width + 24);
  canvas.width = Math.max(selected ? 150 : 116, width);
  canvas.height = selected ? 54 : 42;
  ctx.font = `800 ${fontSize}px Inter, Arial, sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = selected ? "rgba(11, 92, 255, 0.92)" : "rgba(255, 255, 255, 0.9)";
  roundRect(ctx, 0, selected ? 7 : 6, canvas.width, selected ? 40 : 30, selected ? 14 : 10);
  ctx.fill();
  ctx.strokeStyle = selected ? "rgba(11, 92, 255, 0.74)" : "rgba(70, 108, 170, 0.28)";
  ctx.stroke();
  ctx.fillStyle = selected ? "#ffffff" : "#0f1a2e";
  ctx.fillText(label, canvas.width / 2, selected ? 27 : 21);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(canvas.width / (selected ? 128 : 170), selected ? 0.34 : 0.23, 1);
  sprite.userData.isLabel = true;
  return sprite;
}

function roundRect(ctx, x, y, width, height, radius) {
  const r = Math.min(radius, width / 2, height / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + width, y, x + width, y + height, r);
  ctx.arcTo(x + width, y + height, x, y + height, r);
  ctx.arcTo(x, y + height, x, y, r);
  ctx.arcTo(x, y, x + width, y, r);
  ctx.closePath();
}

function graphPositions(nodes) {
  const positions = new Map();
  const clusters = new Map();
  nodes.forEach((node) => {
    const key = node.file || node.module || node.kind || "unknown";
    if (!clusters.has(key)) clusters.set(key, []);
    clusters.get(key).push(node);
  });

  const orderedClusters = [...clusters.entries()].sort((a, b) => b[1].length - a[1].length);
  const golden = Math.PI * (3 - Math.sqrt(5));
  const clusterStep = Math.max(2.6, Math.cbrt(nodes.length) * 0.72);

  orderedClusters.forEach(([, clusterNodes], clusterIndex) => {
    const shell = Math.ceil(Math.cbrt(clusterIndex + 1)) - 1;
    const shellStart = shell === 0 ? 0 : shell * shell * shell;
    const nextShellStart = (shell + 1) * (shell + 1) * (shell + 1);
    const shellSlots = Math.max(1, nextShellStart - shellStart);
    const slot = Math.max(0, clusterIndex - shellStart);
    const t = (slot + 0.5) / shellSlots;
    const y = 1 - t * 2;
    const radial = Math.sqrt(Math.max(0, 1 - y * y));
    const angle = slot * golden + shell * 0.53;
    const distance = shell === 0 ? 0 : shell * clusterStep;
    const center = new THREE.Vector3(
      Math.cos(angle) * radial * distance,
      y * distance,
      Math.sin(angle) * radial * distance,
    );
    const clusterRadius = Math.max(0.48, Math.cbrt(clusterNodes.length) * 0.25);

    clusterNodes.forEach((node, nodeIndex) => {
      const localT = (nodeIndex + 0.5) / Math.max(clusterNodes.length, 1);
      const localY = 1 - localT * 2;
      const localRadial = Math.sqrt(Math.max(0, 1 - localY * localY));
      const localAngle = nodeIndex * golden;
      const localRadius = Math.cbrt(localT) * clusterRadius;
      positions.set(node.id, new THREE.Vector3(
        center.x + Math.cos(localAngle) * localRadial * localRadius,
        center.y + localY * localRadius,
        center.z + Math.sin(localAngle) * localRadial * localRadius,
      ));
    });
  });

  return positions;
}

function centerPositions(positions) {
  const points = [...positions.values()];
  if (!points.length) return 8;

  const box = new THREE.Box3().setFromPoints(points);
  const center = new THREE.Vector3();
  box.getCenter(center);
  let radius = 0;
  positions.forEach((position) => {
    position.sub(center);
    radius = Math.max(radius, position.length());
  });
  return Math.max(4, radius + 1.4);
}

function fitCameraToGraph() {
  if (!state.camera) return;
  const fov = THREE.MathUtils.degToRad(state.camera.fov);
  const aspect = Math.max(0.75, state.camera.aspect || 1);
  const verticalFit = state.graphRadius / Math.tan(fov / 2);
  const horizontalFit = state.graphRadius / Math.tan(fov / 2) / aspect;
  state.overviewZoom = Math.max(9, Math.max(verticalFit, horizontalFit) * 1.08);
  state.maxZoom = Math.max(state.overviewZoom * 2.4, state.overviewZoom + 18);
  state.camera.position.set(0, state.graphRadius * 0.06, state.overviewZoom);
  state.camera.near = Math.max(0.01, state.overviewZoom / 1000);
  state.camera.far = state.maxZoom * 3;
  state.camera.updateProjectionMatrix();
  state.camera.lookAt(0, 0, 0);
}

function ensureScene(canvas) {
  ensureEnhancements();
  if (state.renderer) return;

  state.scene = new THREE.Scene();
  state.scene.background = new THREE.Color(0xf7fbff);
  state.scene.fog = null;

  state.camera = new THREE.PerspectiveCamera(44, 1, 0.1, 1000);
  state.camera.position.set(0, 0.8, state.overviewZoom);

  state.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
  state.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  const ambient = new THREE.AmbientLight(0xffffff, 0.78);
  state.scene.add(ambient);
  const key = new THREE.DirectionalLight(0xffffff, 2.1);
  key.position.set(4, 6, 8);
  state.scene.add(key);
  const rim = new THREE.DirectionalLight(0x9cc7ff, 1.05);
  rim.position.set(-5, -1, -5);
  state.scene.add(rim);

  state.group = new THREE.Group();
  state.scene.add(state.group);

  canvas.addEventListener("pointerdown", onPointerDown);
  canvas.addEventListener("pointermove", onPointerMove);
  canvas.addEventListener("pointerup", onPointerUp);
  canvas.addEventListener("pointerleave", onPointerUp);
  canvas.addEventListener("wheel", onWheel, { passive: false });
  window.addEventListener("resize", resize);

  animate();
}

function resize() {
  const canvas = $("graphCanvas3d");
  if (!canvas || !state.renderer) return;
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(320, Math.floor(rect.width));
  const height = Math.max(320, Math.floor(rect.height));
  state.camera.aspect = width / height;
  state.camera.updateProjectionMatrix();
  state.renderer.setSize(width, height, false);
}

function animate() {
  state.animationId = requestAnimationFrame(animate);
  if (!state.dragging && state.group && state.mode === "orbit") {
    state.group.rotation.y += 0.0014;
  }
  state.renderer?.render(state.scene, state.camera);
}

function resetCamera() {
  if (!state.group || !state.camera) return;
  state.group.rotation.set(-0.22, 0.34, 0);
  fitCameraToGraph();
}

function onPointerDown(event) {
  state.dragging = true;
  state.moved = false;
  state.lastX = event.clientX;
  state.lastY = event.clientY;
  event.currentTarget.setPointerCapture?.(event.pointerId);
}

function onPointerMove(event) {
  if (!state.dragging || !state.group) return;
  const dx = event.clientX - state.lastX;
  const dy = event.clientY - state.lastY;
  if (Math.abs(dx) + Math.abs(dy) > 3) state.moved = true;
  state.group.rotation.y += dx * 0.005;
  state.group.rotation.x += dy * 0.005;
  state.group.rotation.x = Math.max(-1.25, Math.min(1.25, state.group.rotation.x));
  state.lastX = event.clientX;
  state.lastY = event.clientY;
}

function onPointerUp(event) {
  if (!state.dragging) return;
  state.dragging = false;
  event.currentTarget.releasePointerCapture?.(event.pointerId);
  if (!state.moved) pickNode(event);
}

function onWheel(event) {
  event.preventDefault();
  state.camera.position.z = Math.max(state.overviewZoom * 0.18, Math.min(state.maxZoom, state.camera.position.z + event.deltaY * 0.018));
}

function pickNode(event) {
  const canvas = $("graphCanvas3d");
  const rect = canvas.getBoundingClientRect();
  state.pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  state.pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  state.raycaster.setFromCamera(state.pointer, state.camera);
  const hits = state.raycaster.intersectObjects(state.nodeMeshes, false);
  if (hits.length) {
    const hit = hits[0];
    const node = hit.object.userData.nodes?.[hit.instanceId] || hit.object.userData.node;
    if (node) selectNode(node.id);
    return;
  }

  let closest = null;
  let closestDistance = Infinity;
  const worldPosition = new THREE.Vector3();
  state.group.updateMatrixWorld(true);
  state.nodeRecords.forEach((record) => {
    worldPosition.copy(record.position).applyMatrix4(state.group.matrixWorld);
    const distance = state.raycaster.ray.distanceSqToPoint(worldPosition);
    const clickRadius = Math.max(record.radius * 3.2, state.graphRadius * 0.012);
    const clickDistance = clickRadius * clickRadius;
    if (distance <= clickDistance && distance < closestDistance) {
      closest = record;
      closestDistance = distance;
    }
  });
  if (closest) selectNode(closest.node.id);
}

function disposeObject(child) {
  child.geometry?.dispose?.();
  const disposeMaterial = (material) => {
    material?.map?.dispose?.();
    material?.dispose?.();
  };
  if (Array.isArray(child.material)) child.material.forEach(disposeMaterial);
  else disposeMaterial(child.material);
}

function clearGroup() {
  while (state.group.children.length) {
    const child = state.group.children.pop();
    disposeObject(child);
  }
  state.nodeMeshes = [];
  state.nodeById.clear();
  state.nodeRecords = [];
  state.selectedMesh = null;
  state.selectedMarker = null;
  state.selectedLabel = null;
  state.selectedNodeId = "";
}

function edgeColor(kind) {
  if (/call/i.test(kind || "")) return 0x0b5cff;
  if (/import|depend/i.test(kind || "")) return 0xf59e0b;
  if (/contain|define/i.test(kind || "")) return 0x059669;
  return 0x7a8aa0;
}

function addBatchedEdges(edges, positions, nodeSet) {
  const batches = new Map();
  edges.forEach((edge) => {
    if (!nodeSet.has(edge.source) || !nodeSet.has(edge.target)) return;
    const a = positions.get(edge.source);
    const b = positions.get(edge.target);
    if (!a || !b) return;
    const color = edgeColor(edge.kind);
    if (!batches.has(color)) batches.set(color, []);
    batches.get(color).push(a.x, a.y, a.z, b.x, b.y, b.z);
  });

  batches.forEach((points, color) => {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(points, 3));
    const material = new THREE.LineBasicMaterial({
      color,
      transparent: true,
      opacity: 0.34,
    });
    state.group.add(new THREE.LineSegments(geometry, material));
  });
}

function addInstancedNodes(nodes, positions) {
  const sphere = new THREE.SphereGeometry(1, nodes.length > 5000 ? 8 : 14, nodes.length > 5000 ? 6 : 10);
  const grouped = new Map();
  nodes.forEach((node) => {
    const color = colorForNode(node);
    if (!grouped.has(color)) grouped.set(color, []);
    grouped.get(color).push(node);
  });

  const matrix = new THREE.Matrix4();
  grouped.forEach((groupNodes, color) => {
    const material = new THREE.MeshStandardMaterial({
      color,
      roughness: 0.42,
      metalness: 0.04,
      emissive: 0x000000,
    });
    const mesh = new THREE.InstancedMesh(sphere, material, groupNodes.length);
    mesh.userData.nodes = groupNodes;
    mesh.instanceMatrix.setUsage(THREE.StaticDrawUsage);

    groupNodes.forEach((node, index) => {
      const position = positions.get(node.id);
      const radius = radiusForNode(node);
      matrix.compose(
        position,
        new THREE.Quaternion(),
        new THREE.Vector3(radius, radius, radius),
      );
      mesh.setMatrixAt(index, matrix);
      const record = { node, position, radius, mesh, instanceId: index, label: null };
      state.nodeById.set(node.id, record);
      state.nodeRecords.push(record);
    });

    mesh.instanceMatrix.needsUpdate = true;
    state.group.add(mesh);
    state.nodeMeshes.push(mesh);
  });
}

function colorForCluster(name, index) {
  let hash = 0;
  String(name || "").split("").forEach((char) => {
    hash = ((hash << 5) - hash + char.charCodeAt(0)) | 0;
  });
  const hue = ((Math.abs(hash) + index * 37) % 360) / 360;
  return new THREE.Color().setHSL(hue, 0.58, 0.48);
}

function addFileClusterSpheres(nodes, positions) {
  const clusters = new Map();
  nodes.forEach((node) => {
    const key = node.file || node.module || "unknown";
    const position = positions.get(node.id);
    if (!position) return;
    if (!clusters.has(key)) {
      clusters.set(key, { nodes: [], points: [], center: new THREE.Vector3() });
    }
    const cluster = clusters.get(key);
    cluster.nodes.push(node);
    cluster.points.push(position);
    cluster.center.add(position);
  });

  [...clusters.entries()]
    .filter(([, cluster]) => cluster.nodes.length > 1)
    .sort((a, b) => b[1].nodes.length - a[1].nodes.length)
    .forEach(([name, cluster], index) => {
      cluster.center.multiplyScalar(1 / cluster.points.length);
      let radius = 0;
      cluster.points.forEach((point, pointIndex) => {
        const nodeRadius = radiusForNode(cluster.nodes[pointIndex]);
        radius = Math.max(radius, point.distanceTo(cluster.center) + nodeRadius);
      });
      radius = Math.max(radius + 0.28, 0.55);

      const geometry = new THREE.SphereGeometry(radius, 28, 18);
      const material = new THREE.MeshBasicMaterial({
        color: colorForCluster(name, index),
        transparent: true,
        opacity: 0.18,
        wireframe: true,
        depthWrite: false,
      });
      const sphere = new THREE.Mesh(geometry, material);
      sphere.position.copy(cluster.center);
      sphere.userData.isFileCluster = true;
      sphere.userData.file = name;
      state.group.add(sphere);
    });
}

function addImportantLabels(nodes, positions) {
  const labelBudget = Math.min(nodes.length, nodes.length > 5000 ? 120 : 260);
  nodes.slice(0, labelBudget).forEach((node) => {
    const record = state.nodeById.get(node.id);
    const position = positions.get(node.id);
    if (!record || !position) return;
    const label = makeLabelSprite(node.name || node.kind || "node");
    label.position.copy(position);
    label.position.y += record.radius + state.graphRadius * 0.008;
    record.label = label;
    state.group.add(label);
  });
}

function addClusterLabels(nodes, positions) {
  const clusters = new Map();
  nodes.forEach((node) => {
    const key = node.file || node.module || node.kind || "unknown";
    if (!clusters.has(key)) clusters.set(key, { nodes: [], center: new THREE.Vector3() });
    const cluster = clusters.get(key);
    cluster.nodes.push(node);
    cluster.center.add(positions.get(node.id));
  });

  [...clusters.entries()]
    .sort((a, b) => b[1].nodes.length - a[1].nodes.length)
    .slice(0, 48)
    .forEach(([name, cluster]) => {
      cluster.center.multiplyScalar(1 / cluster.nodes.length);
      const label = makeLabelSprite(`${name} (${cluster.nodes.length})`, false);
      label.scale.multiplyScalar(0.82);
      label.position.copy(cluster.center);
      label.position.y += Math.max(0.6, Math.sqrt(cluster.nodes.length) * 0.05);
      state.group.add(label);
    });
}

function addSelectedMarker(record) {
  if (state.selectedMarker) {
    state.group.remove(state.selectedMarker);
    disposeObject(state.selectedMarker);
  }
  if (state.selectedLabel) {
    state.group.remove(state.selectedLabel);
    disposeObject(state.selectedLabel);
  }

  const marker = new THREE.Mesh(
    new THREE.SphereGeometry(1, 18, 12),
    new THREE.MeshStandardMaterial({
      color: colorForNode(record.node),
      roughness: 0.28,
      metalness: 0.08,
      emissive: 0x0b5cff,
      emissiveIntensity: 0.25,
    }),
  );
  marker.position.copy(record.position);
  marker.scale.setScalar(record.radius * 2.5);
  state.group.add(marker);
  state.selectedMarker = marker;

  const label = makeLabelSprite(record.node.name || record.node.kind || "node", true);
  label.position.copy(record.position);
  label.position.y += record.radius + state.graphRadius * 0.018;
  state.group.add(label);
  state.selectedLabel = label;
}

function renderGraph3D(data) {
  const canvas = $("graphCanvas3d");
  ensureScene(canvas);
  resize();
  clearGroup();

  const nodes = data.nodes || [];
  const edges = data.edges || [];
  const empty = $("graphEmptyState");
  if (empty) {
    empty.classList.toggle("show", !nodes.length);
    empty.textContent = nodes.length ? "" : "No displayable graph nodes were returned.";
  }
  if (!nodes.length) return;

  const positions = graphPositions(nodes, edges);
  state.graphRadius = centerPositions(positions);
  const nodeSet = new Set(nodes.map((node) => node.id));

  addFileClusterSpheres(nodes, positions);
  addBatchedEdges(edges, positions, nodeSet);
  addInstancedNodes(nodes, positions);
  addClusterLabels(nodes, positions);
  addImportantLabels(nodes, positions);

  resetCamera();
  selectNode(nodes[0].id);
}

function renderNodeShell(node, loading = false) {
  const lines = node.line_start ? `:${node.line_start}${node.line_end ? "-" + node.line_end : ""}` : "";
  const metadata = [
    ["Kind", node.kind || "Node"],
    ["Language", node.language || ""],
    ["Parent", node.parent_name || ""],
    ["Return", node.return_type || ""],
  ].filter(([, value]) => value);

  return `<div class="graph-node-detail__label">Selected node</div>
    <h4>${escapeHtml(node.name || node.id)}</h4>
    <div class="kg-node-meta">
      ${metadata.map(([key, value]) => `<div><span>${escapeHtml(key)}</span><strong>${escapeHtml(value)}</strong></div>`).join("")}
    </div>
    <div class="kg-node-file"><span>File</span><code>${escapeHtml(node.file || "")}${lines}</code></div>
    ${loading ? `<div class="graph-code-status">Loading source code for this node...</div>` : ""}`;
}

function selectNode(id) {
  const record = state.nodeById.get(id);
  if (!record) return;

  state.selectedMesh = record.mesh;
  state.selectedNodeId = id;
  addSelectedMarker(record);

  if (state.mode === "focus") {
    state.group.rotation.y = -Math.atan2(record.position.x, record.position.z);
  }

  document.querySelectorAll(".graph-node-row").forEach((row) => {
    row.classList.toggle("active", row.dataset.nodeId === id);
  });

  const detail = $("graphDetail");
  const node = record.node;
  if (detail) detail.innerHTML = renderNodeShell(node, true);
  loadNodeSource(id);
}

async function loadNodeSource(id) {
  const request = window.currentGraphRequest;
  const detail = $("graphDetail");
  if (!request || !detail) return;

  const pr = request.prNumber ? `&pr_number=${encodeURIComponent(request.prNumber)}` : "";
  try {
    const response = await fetch(
      `/api/graph/${encodeURIComponent(request.owner)}/${encodeURIComponent(request.name)}/node?qualified_name=${encodeURIComponent(id)}${pr}`,
    );
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Could not load node source");
    if (state.selectedNodeId !== id) return;

    const node = data.node || {};
    const code = data.code_snippet || "";
    const start = data.snippet_start_line || node.line_start || 1;
    const end = data.snippet_end_line || node.line_end || start;
    const truncated = data.code_truncated ? " · truncated" : "";
    const codeHtml = code
      ? code.split("\n").map((line, idx) => `<span class="graph-code-line">
          <span class="graph-code-line__no">${start + idx}</span>
          <span>${escapeHtml(line)}</span>
        </span>`).join("")
      : "";

    detail.innerHTML = `${renderNodeShell(node, false)}
      ${codeHtml
        ? `<div class="graph-code-box">
            <div class="graph-code-box__header">
              <span>Source code</span>
              <span>L${start}-L${end}${truncated}</span>
            </div>
            <pre>${codeHtml}</pre>
          </div>`
        : `<div class="graph-code-status">Source code is not available for this node. The graph may point to a file path that is no longer mounted locally.</div>`}`;
  } catch (error) {
    if (state.selectedNodeId !== id) return;
    const status = detail.querySelector(".graph-code-status");
    if (status) status.textContent = error.message;
  }
}

window.Graph3D = {
  render: renderGraph3D,
  select: selectNode,
  resize,
};

if (window.pendingGraphData) renderGraph3D(window.pendingGraphData);
