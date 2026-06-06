import { state, colors, mapZoom } from '../state.js';
import { els, data, three, isSpcPrepCandidate, selectedMapFocus } from '../dataLoader.js';
import { filteredCandidates } from './candidateList.js';

export function map3dPosition(candidate) {
  return {
    x: candidate.map.x * 1.85,
    y: candidate.map.y * 1.85,
    z: (candidate.map.z - 0.45) * 2.4
  };
}

export function update3dCameraZoom() {
  if (!state.sceneReady || !three.camera) return;
  const focus = selectedMapFocus();
  const zoomFocus = Math.max(0, Math.min(1, (mapZoom - 1) / 4));
  const target = new THREE.Vector3(0, 0, 0);
  if (focus && three.selectedMesh) {
    three.scene.updateMatrixWorld();
    three.selectedMesh.getWorldPosition(target);
    target.multiplyScalar(zoomFocus);
  }
  three.camera.position.x = target.x;
  three.camera.position.y = target.y;
  three.camera.position.z = 4.8 / Math.sqrt(mapZoom);
  three.camera.lookAt(target);
  three.camera.updateProjectionMatrix();
}

export function update3dData() {
  if (!state.sceneReady) return;
  const candidates = filteredCandidates().filter((candidate) => candidate.color !== "gray");
  const temp = new THREE.Object3D();
  ["green", "spc-prep", "yellow", "red", "gray"].forEach((key) => {
    const subset = candidates.filter((candidate) => key === "spc-prep" ? isSpcPrepCandidate(candidate) : (!isSpcPrepCandidate(candidate) && candidate.color === key));
    subset.forEach((candidate, index) => {
      const position = map3dPosition(candidate);
      const scale = Math.max(0.9, Math.min(1.25, 0.9 + Math.sqrt(Number(candidate.snr || 0)) / 40));
      temp.position.set(position.x, position.y, position.z);
      temp.scale.setScalar(scale);
      temp.updateMatrix();
      three.groups[key].mesh.setMatrixAt(index, temp.matrix);
    });
    three.groups[key].mesh.count = subset.length;
    three.groups[key].mesh.instanceMatrix.needsUpdate = true;
  });
  update3dSelection();
}

export function update3dSelection() {
  if (!state.sceneReady || !state.selected) return;
  const position = map3dPosition(state.selected);
  three.selectedMesh.position.set(position.x, position.y, position.z);
  update3dCameraZoom();
}

export function resize3d() {
  if (!state.sceneReady) return;
  const rect = els.map3d.getBoundingClientRect();
  three.renderer.setSize(Math.max(1, rect.width), Math.max(1, rect.height), false);
  three.camera.aspect = Math.max(1, rect.width) / Math.max(1, rect.height);
  three.camera.updateProjectionMatrix();
}

export function animate3d() {
  if (!state.sceneReady) return;
  three.rotation += 0.003;
  three.scene.rotation.y = three.rotation;
  three.scene.rotation.x = -0.18;
  if (three.earthMesh) {
    const orbit = three.rotation * 3.4;
    three.earthMesh.position.set(Math.cos(orbit) * 0.173, 0, Math.sin(orbit) * 0.173);
  }
  update3dCameraZoom();
  three.renderer.render(three.scene, three.camera);
  requestAnimationFrame(animate3d);
}

export function init3dMap() {
  if (!window.THREE || state.sceneReady) return;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  els.map3d.innerHTML = "";
  els.map3d.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 100);
  camera.position.set(0, 0, 4.8);
  scene.add(new THREE.AmbientLight(0xffffff, 0.9));

  const referenceGroup = new THREE.Group();
  const sunMesh = new THREE.Mesh(
    new THREE.SphereGeometry(0.07, 18, 18),
    new THREE.MeshBasicMaterial({ color: 0xf4c96d })
  );
  const sunHalo = new THREE.Mesh(
    new THREE.SphereGeometry(0.12, 16, 16),
    new THREE.MeshBasicMaterial({ color: 0xf4c96d, transparent: true, opacity: 0.2 })
  );
  const earthOrbit = new THREE.Mesh(
    new THREE.RingGeometry(0.17, 0.176, 56),
    new THREE.MeshBasicMaterial({ color: 0x95a9c4, side: THREE.DoubleSide, transparent: true, opacity: 0.7 })
  );
  earthOrbit.rotation.x = Math.PI / 2;
  const earthMesh = new THREE.Mesh(
    new THREE.SphereGeometry(0.02, 12, 12),
    new THREE.MeshBasicMaterial({ color: 0x84c7ff })
  );
  earthMesh.position.set(0.173, 0, 0);
  referenceGroup.add(earthOrbit);
  referenceGroup.add(sunHalo);
  referenceGroup.add(sunMesh);
  referenceGroup.add(earthMesh);
  scene.add(referenceGroup);

  const northSouthAxis = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(0, 0, -1.25),
    new THREE.Vector3(0, 0, 1.25)
  ]);
  const northSouthLine = new THREE.Line(
    northSouthAxis,
    new THREE.LineDashedMaterial({
      color: 0xffffff,
      transparent: true,
      opacity: 0.26,
      dashSize: 0.08,
      gapSize: 0.08
    })
  );
  northSouthLine.computeLineDistances();
  scene.add(northSouthLine);

  const groups = {};
  const maxInstances = Math.max(1, (data.candidates || []).length);
  ["green", "spc-prep", "yellow", "red", "gray"].forEach((key) => {
    const geometry = new THREE.SphereGeometry(0.0065, 12, 10);
    const material = new THREE.MeshBasicMaterial({
      color: key === "spc-prep" ? colors.spcPrep : colors[key],
      transparent: true,
      opacity: 0.9
    });
    const mesh = new THREE.InstancedMesh(geometry, material, maxInstances);
    mesh.count = 0;
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    groups[key] = { mesh };
    scene.add(mesh);
  });

  const selectedGeometry = new THREE.SphereGeometry(0.028, 16, 12);
  const selectedMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff, wireframe: true });
  const selectedMesh = new THREE.Mesh(selectedGeometry, selectedMaterial);
  scene.add(selectedMesh);

  Object.assign(three, { renderer, scene, camera, groups, selectedMesh, earthMesh, rotation: 0 });
  state.sceneReady = true;
  update3dCameraZoom();
  update3dData();
  resize3d();
  animate3d();
}
