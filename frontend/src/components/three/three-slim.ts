/**
 * Slim `three` entry for the production bundle (DECISIONS D25). React Three Fiber v8 imports
 * the whole THREE namespace (`import * as THREE` + `extend(THREE)`), which defeats tree shaking
 * and pushes the 3D chunk past its 220 KB gzip budget (spec §13.12). vite.config.ts aliases the
 * bare `three` specifier to this module, which re-exports only what R3F, the two drei helpers
 * and our scene use, from three's tree-shakeable sources. `three-slim.test.ts` scans those
 * libraries and fails if anything they reference is missing here.
 */
/* eslint-disable @typescript-eslint/no-deprecated -- R3F v8 still references Clock and
   PCFSoftShadowMap; re-exporting them is required, not a new use. */
export {
  ACESFilmicToneMapping,
  AdditiveBlending,
  AmbientLight,
  BasicShadowMap,
  BufferAttribute,
  BufferGeometry,
  Camera,
  Clock,
  Color,
  ColorManagement,
  DirectionalLight,
  DoubleSide,
  Group,
  IcosahedronGeometry,
  InstancedMesh,
  Layers,
  LineBasicMaterial,
  LineSegments,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  NoToneMapping,
  Object3D,
  OrthographicCamera,
  PCFShadowMap,
  PCFSoftShadowMap,
  PerspectiveCamera,
  PlaneGeometry,
  PMREMGenerator,
  Raycaster,
  RGBAFormat,
  Scene,
  UnsignedByteType,
  Vector2,
  Vector3,
  VSMShadowMap,
  WebGLRenderer,
} from "three/src/Three.js";
