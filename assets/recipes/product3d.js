/*! product3d.js - studio product shots with three.js (MIT). Deterministic: draw from time only.
 *
 * Setup (once per composition):
 *   python3 scripts/fetch_assets.py npm COMP three build/three.module.js build/three.core.js \
 *       examples/jsm/environments/RoomEnvironment.js examples/jsm/geometries/RoundedBoxGeometry.js
 *   cp <skill>/assets/recipes/product3d.js COMP/assets/recipes/
 * In index.html, before your module script:
 *   <script type="importmap">{"imports":{"three":"./assets/vendor/three/build/three.module.js",
 *     "three/addons/":"./assets/vendor/three/examples/jsm/"}}</script>
 * ES modules need http://, so preview with: render.py COMP --serve
 *
 * Speed: on machines without a GPU (most cloud sandboxes) WebGL runs in software.
 * Size the canvas to the product, not the whole frame; use mat.glassFast while iterating;
 * keep 3D to the scenes that need it. render.py prints an ETA after the first frames.
 * Refractive glass (mat.glass) refracts the 3D scene, not the page behind the canvas:
 * pass studio(canvas, {background: '<scene colour>'}) and put any CSS vignette on top.
 *
 *   import { studio, lathe, box, mat, profiles } from './assets/recipes/product3d.js';
 *   const s = studio(document.querySelector('#hero canvas'));
 *   const bottle = lathe(profiles.bottle(), mat.glass('#d9f1ff'));
 *   s.add(bottle);
 *   Stage.scene('hero', sc => sc.frame((t) => { bottle.rotation.y = 0.4 + t * 0.5; s.render(); }));
 */
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

export { THREE };

// Canvas + renderer + soft studio light. The canvas keeps its CSS size; pixels match the stage.
export function studio(canvas, o = {}) {
  o = Object.assign({ fov: 30, camera: [0, 0.35, 6.2], target: [0, 0.1, 0], exposure: 1.0, background: null, floor: true, floorColor: 0x000000, floorOpacity: 0.28, antialias: true, pixelRatio: null }, o);
  const W = canvas.clientWidth || canvas.width, H = canvas.clientHeight || canvas.height;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: o.antialias, alpha: o.background == null, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
  // follows the render scale: draft renders (half size) draw the 3D at half size too
  renderer.setPixelRatio(o.pixelRatio || Math.min(1, window.devicePixelRatio || 1));
  renderer.setSize(W, H, false);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = o.exposure;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  if (o.background != null) scene.background = new THREE.Color(o.background);
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  const camera = new THREE.PerspectiveCamera(o.fov, W / H, 0.05, 100);
  camera.position.set(...o.camera);
  camera.lookAt(...o.target);
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(3, 4, 5);
  const rim = new THREE.DirectionalLight(0xffffff, 1.2);
  rim.position.set(-4, 2, -3);
  scene.add(key, rim);
  let floor = null;
  if (o.floor) {
    // soft contact shadow: a radial gradient disc, no shadow maps needed
    const c = document.createElement('canvas');
    c.width = c.height = 256;
    const g = c.getContext('2d');
    const grd = g.createRadialGradient(128, 128, 0, 128, 128, 128);
    grd.addColorStop(0, 'rgba(0,0,0,1)');
    grd.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grd;
    g.fillRect(0, 0, 256, 256);
    const tex = new THREE.CanvasTexture(c);
    floor = new THREE.Mesh(new THREE.PlaneGeometry(2.2, 2.2), new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: o.floorOpacity, color: o.floorColor, depthWrite: false }));
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -1.0;
    scene.add(floor);
  }
  const root = new THREE.Group();
  scene.add(root);
  return {
    renderer, scene, camera, root, floor, THREE,
    add(...objs) { root.add(...objs); return this; },
    resize() { const w = canvas.clientWidth, h = canvas.clientHeight; renderer.setSize(w, h, false); camera.aspect = w / h; camera.updateProjectionMatrix(); },
    render() { if (window.__onevideoQA) return; renderer.render(scene, camera); },   // QA sampling only needs layout
    orbit(angle, radius = 6.2, height = 0.35) { camera.position.set(Math.sin(angle) * radius, height, Math.cos(angle) * radius); camera.lookAt(...o.target); },
    // stage-pixel position of a point on an object (for callout lines and labels that follow the product)
    point(obj, local = [0, 0, 0]) {
      const v = new THREE.Vector3(...local);
      obj.updateWorldMatrix(true, false);
      obj.localToWorld(v);
      v.project(camera);
      const r = canvas.getBoundingClientRect();
      const st = document.getElementById('stage').getBoundingClientRect();
      const k = st.width / (window.Stage ? window.Stage.W : st.width);
      return { x: ((v.x + 1) / 2 * r.width + r.left - st.left) / k, y: ((1 - v.y) / 2 * r.height + r.top - st.top) / k, behind: v.z > 1 };
    },
  };
}

// Materials tuned to read well in a studio render.
export const mat = {
  // refractive glass (transmission): best look, ~3x slower on CPU-only machines.
  // Anything seen through it (liquid, labels, parts) must be non-transmissive to show up.
  glass: (tint = '#e8f6ff', o = {}) => new THREE.MeshPhysicalMaterial(Object.assign({ color: tint, metalness: 0, roughness: 0.04, transmission: 1, thickness: 0.35, ior: 1.5, clearcoat: 1, clearcoatRoughness: 0.03, side: THREE.DoubleSide }, o)),
  // cheap glass: reflections + faint body, no refraction pass
  glassFast: (tint = '#dfeff8', o = {}) => new THREE.MeshPhysicalMaterial(Object.assign({ color: tint, metalness: 0, roughness: 0.02, clearcoat: 1, clearcoatRoughness: 0.02, transparent: true, opacity: 0.16, envMapIntensity: 1.6, depthWrite: false, side: THREE.DoubleSide }, o)),
  frosted: (tint = '#ffffff', o = {}) => new THREE.MeshPhysicalMaterial(Object.assign({ color: tint, roughness: 0.45, transmission: 0.9, thickness: 0.6, ior: 1.45 }, o)),
  metal: (color = '#c9ccd2', rough = 0.28, o = {}) => new THREE.MeshPhysicalMaterial(Object.assign({ color, metalness: 1, roughness: rough, clearcoat: 0.3 }, o)),
  plastic: (color = '#ff6a3d', o = {}) => new THREE.MeshPhysicalMaterial(Object.assign({ color, roughness: 0.38, clearcoat: 0.6, clearcoatRoughness: 0.25 }, o)),
  matte: (color = '#2b2f36', o = {}) => new THREE.MeshStandardMaterial(Object.assign({ color, roughness: 0.85, metalness: 0 }, o)),
  ceramic: (color = '#f3efe8', o = {}) => new THREE.MeshPhysicalMaterial(Object.assign({ color, roughness: 0.22, clearcoat: 1, clearcoatRoughness: 0.08 }, o)),
  rubber: (color = '#1d1f23', o = {}) => new THREE.MeshStandardMaterial(Object.assign({ color, roughness: 0.95 }, o)),
  wood: (color = '#a9784f', o = {}) => new THREE.MeshStandardMaterial(Object.assign({ color, roughness: 0.7 }, o)),
  liquid: (color = '#c47a2c', o = {}) => new THREE.MeshPhysicalMaterial(Object.assign({ color, roughness: 0.08, clearcoat: 1, clearcoatRoughness: 0.05, sheen: 0.4, sheenColor: color }, o)),
};

// Revolve a 2D profile [[radius, y], ...] (bottom to top) into a solid: bottles, cups, jars, vases, lamps, cans.
export function lathe(profile, material, segments = 96) {
  const pts = profile.map(([r, y]) => new THREE.Vector2(Math.max(0.0001, r), y));
  const g = new THREE.LatheGeometry(pts, segments);
  g.computeVertexNormals();
  return new THREE.Mesh(g, material);
}

// Rounded box for phones, speakers, packaging, books, cards.
export function box(w, h, d, radius, material, seg = 6) {
  return new THREE.Mesh(new RoundedBoxGeometry(w, h, d, seg, radius), material);
}

export function cylinder(r, h, material, rTop = r) {
  return new THREE.Mesh(new THREE.CylinderGeometry(rTop, r, h, 96, 1), material);
}

// Ready-made profiles (units: the object is about 2 tall, centred on y = 0).
export const profiles = {
  bottle: (w = 0.42) => [[0.0, -1.0], [w * 0.92, -1.0], [w, -0.94], [w, 0.38], [w * 0.92, 0.5], [w * 0.62, 0.62], [w * 0.5, 0.72], [w * 0.5, 0.86]],
  cup: (w = 0.55) => [[0, -0.6], [w * 0.78, -0.6], [w * 0.84, -0.55], [w, 0.55], [w * 0.97, 0.6], [w * 0.92, 0.6], [w * 0.8, -0.5], [0, -0.5]],
  jar: (w = 0.6) => [[0, -0.7], [w, -0.7], [w * 1.02, -0.6], [w * 1.02, 0.45], [w * 0.9, 0.55], [w * 0.9, 0.7]],
  vase: (w = 0.5) => [[0, -1], [w * 0.7, -1], [w, -0.6], [w * 1.05, -0.1], [w * 0.6, 0.55], [w * 0.45, 0.8], [w * 0.55, 0.95]],
  can: (w = 0.38) => [[0, -0.8], [w * 0.86, -0.8], [w, -0.72], [w, 0.7], [w * 0.88, 0.8], [0, 0.8]],
  candle: (w = 0.5) => [[0, -0.5], [w, -0.5], [w, 0.5], [0, 0.5]],
  lid: (w = 0.26, h = 0.28) => [[0, 0], [w, 0], [w * 1.02, 0.02], [w * 1.02, h * 0.9], [w * 0.95, h], [0, h]],
};

// Deterministic helpers
export const turn = (t, degPerSec = 24, start = 0) => (start + degPerSec * t) * Math.PI / 180;
export const float = (t, amp = 0.04, period = 4) => Math.sin((t / period) * Math.PI * 2) * amp;
