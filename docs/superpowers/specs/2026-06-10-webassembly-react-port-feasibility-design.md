# RAC-6 WebAssembly / React Port Feasibility Design

## 结论

`race-overlay` 可以做成无后端的浏览器端产品，并提供 React 调用形态 `<RaceOverlay />`，但不建议把现有 Python CLI 直接整体编译成 WebAssembly。

推荐路线是：保留现有 Python 版本作为迁移期行为基准，同时为浏览器实现一套 TypeScript/React 运行时。浏览器版复用当前的 HUD schema、活动数据模型、插值和对齐语义，但用 Canvas / OffscreenCanvas 重写 HUD 绘制，用浏览器媒体 API 处理预览与导出。最终运行形态不依赖 Python 后端。

RAC-6 应先做一个可度量的 Spike，再决定是否进入生产级迁移。Spike 的目标不是完成全部功能，而是证明浏览器端是否能稳定处理真实视频、真实 TCX、HUD 预览和短片段导出。

## 当前系统可迁移性

### 可直接移植语义的部分

- HUD schema：`HudConfig`、`HudThemeConfig`、`HudWidgetConfig` 已经是简单结构化数据，适合转成 TypeScript 类型和 JSON schema。
- 活动采样：`ActivityTrack`、`ActivitySample`、`ActivityLap`、`HudSample` 是清晰的数据模型。
- 时间轴逻辑：`sample_at`、lap waterfall 状态计算、clip/activity 对齐可以按现有测试语义移植。
- 编辑器概念：当前 browser editor 已经以前端 draft state、preview、inspector、layers 为核心，产品交互不需要重想。

### 不适合直接搬进 WASM 的部分

- `ffmpeg.py` 和 `video_probe.py` 依赖本机 `ffmpeg` / `ffprobe` 进程，浏览器不能直接启动本地进程。
- `pipeline.py` 依赖本地文件系统、缓存目录、逐帧 PNG/MOV 中间产物和 subprocess 管道。
- `hud.py` 使用 Pillow 绘制；即使用 Pyodide 跑 Python，也会带来较大的运行时体积和较差的 React 集成体验。
- `editor_server.py` 是本地 HTTP server + macOS picker，浏览器版应改成组件内状态和用户选择的 `File` / `FileSystemFileHandle`。

## 推荐架构

### React API

浏览器版暴露一个 React 组件和一个底层 runtime：

```tsx
<RaceOverlay
  activityFile={activityFile}
  videoFile={videoFile}
  initialHud={hudConfig}
  onHudChange={setHudConfig}
  onExportProgress={setProgress}
  onExportComplete={handleBlob}
/>
```

组件负责 UI：文件选择、HUD 编辑、预览、导出状态。底层 runtime 负责解析活动文件、采样、绘制 HUD、合成视频。

### 数据流

1. 用户在浏览器选择 TCX 和视频文件。
2. Activity parser 把文件转为 `ActivityTrack`。
3. Video metadata adapter 优先从浏览器可读的 MP4/MOV 容器 metadata 读取 `creation_time`；读不到时返回 `needsExternalApi`，由可插拔外部 API 或手动 offset 兜底。
4. Timeline engine 复用当前 `alignment.py` 的语义。
5. HUD renderer 在 Canvas / OffscreenCanvas 上按现有 schema 绘制透明 overlay。
6. Preview path 用 `<video>` + `<canvas>` 实时叠加显示。
7. Export path 在当前 Spike 实现选择 `MediaRecorder` + canvas capture stream，用短片段 WebM 导出先验证浏览器内合成可行性。

### 为什么不是整包 Python WASM

Pyodide 可用于运行 Python 逻辑，但这里的核心瓶颈不是普通 Python 计算，而是视频 decode/encode、canvas compositing、文件访问和 React UI 集成。把 Python、Pillow 和 FFmpeg 都塞进浏览器会让包体、初始化时间和内存风险同时变大。TypeScript runtime 更容易与 React、Worker、Canvas、WebCodecs 和浏览器权限模型贴合。

## 浏览器技术选择

### HUD 绘制

使用 Canvas 2D 作为 V1 目标。现有 HUD 是文本、面板、路线图、进度条和简单形状，Canvas 2D 足够覆盖。绘制应放进 Worker + OffscreenCanvas，避免长视频导出时阻塞 React UI。MDN 记录 OffscreenCanvas 可在 worker 中离屏渲染，适合这个场景。

### 视频预览

预览不需要导出文件，只需要把 `<video>` 当前帧与 HUD canvas 叠加。这里可以做到真正无后端，且应该优先完成。

### 视频导出

导出是最大风险。建议分两级：

- V1 Spike：短片段导出，目标 5-15 秒，验证 720p/1080p 内存、速度、音频处理和文件可下载。
- 生产版：分块处理长视频，支持取消、进度、错误恢复，并明确浏览器兼容矩阵。

当前 Spike 实现选择 `MediaRecorder`，因为它能在普通浏览器部署条件下完成 canvas 合成和短片段导出，不需要把 Python、ffmpeg 或 FFmpeg WASM 搬进前端包。WebCodecs 和 FFmpeg WASM 保留为后续生产级评估路径：WebCodecs 提供低层视频编码/解码接口，但具体 codec 支持取决于浏览器和设备；FFmpeg WASM 是可能的兜底，但多线程构建通常需要 SharedArrayBuffer 和跨源隔离响应头，部署方必须能设置 COOP/COEP。

### 文件访问

React 组件应支持普通 `<input type="file">` 作为跨浏览器基础能力。File System Access API 可作为增强能力，用于更好的本地文件选择和输出目录体验，但 MDN 标记 `showOpenFilePicker()` 为 limited availability，不能作为唯一方案。

## Spike 范围

Spike 新增一个独立的 web package，不改动 Python 生产渲染路径。

建议目录：

- `web/`：Vite + React + TypeScript demo app/package。
- `web/src/runtime/`：activity parser、sampling、alignment、HUD schema/types、renderer、export worker。
- `web/src/components/RaceOverlay.tsx`：公开 React 组件。
- `web/tests/`：TypeScript 单元测试和少量浏览器集成测试。

Spike 必须实现：

- 读取 TCX fixture 并生成与 Python 等价的 samples/laps。
- 移植 `sample_at`、lap waterfall、alignment 的关键测试。
- 基于当前 HUD schema 用 Canvas 绘制静态 preview。
- `<RaceOverlay />` 接受 activity/video/HUD props 并显示可播放预览。
- 导出 5-15 秒短视频 blob，记录耗时、峰值内存、输出大小和浏览器支持情况。

Spike 明确不做：

- 完整 HUD editor 迁移。
- 全量 widget 100% 像素级 parity。
- 长视频批量导出。
- H.265/HDR/attached picture/audio passthrough 的生产级兼容。
- 替换现有 CLI。

## 验收标准

RAC-6 的 Spike 验收应以可运行原型和数据为准：

- 无后端服务：预览和短片段导出在浏览器内完成。
- React 调用：demo 使用 `<RaceOverlay />` 完成文件选择、预览和导出。
- 数据等价：TCX 解析、采样和对齐关键测试与 Python fixtures 一致。
- 性能记录：至少记录 720p 与 1080p、5 秒导出的耗时和内存观察。
- 风险清单：给出 Go / No-Go 建议，特别是长视频导出、音频、Safari/Firefox/Chrome 兼容和部署头要求。

## 本地证据

当前 Python HUD renderer 的绘制成本不是主要风险。使用 `tests/fixtures/sample_activity.tcx` 和当前 `overlay.yaml` 的 HUD 配置，在本机测得：

- 1280x720，50 frames，baseline mean 约 13.07 ms/frame。
- 1920x1080，50 frames，baseline mean 约 13.94 ms/frame。

这说明浏览器端预览和短片段 HUD 绘制有现实可行性。真正需要 Spike 证明的是 browser video export pipeline，而不是普通 HUD 绘制。

当前 RAC-6 portability 验证基线为：

- `cd web && npm test -- --run`：17 files / 61 tests passed。
- `cd web && npm run build`：demo app、type declarations 和 library bundle 均构建通过。
- `PYTHONPATH=src uv run pytest -q tests/test_tcx_reader.py tests/test_sampling.py tests/test_alignment.py tests/test_portability_contract.py`：37 passed。
- `git diff --check`：无 whitespace error。

## 主要风险

- 浏览器导出长视频可能遇到内存、性能和 tab 生命周期限制。
- WebCodecs codec 支持随浏览器/设备变化，不能保证与本机 FFmpeg 一致。
- FFmpeg WASM 包体和初始化时间较大，多线程部署还需要跨源隔离。
- 浏览器无法可靠读取所有视频容器里的 creation time；应使用浏览器解析作为默认路径，并把难以覆盖的容器交给可插拔外部 API provider 或手动同步。
- Canvas 字体渲染和 Pillow 不会天然像素一致，浏览器版应以视觉等价为目标，而不是逐像素一致。

## 推荐下一步

1. 新建 `web/` Spike package，保持与 Python CLI 隔离。
2. 从类型和测试开始，先移植 models、HUD schema、sampling、alignment。
3. 实现 Canvas HUD preview，只支持当前默认 preset 涉及的 widget。
4. 实现 `<RaceOverlay />` demo，先完成浏览器内 preview。
5. 使用当前 `MediaRecorder` export path 记录 720p/1080p、5 秒导出报告。
6. 用真实短视频和 TCX 记录性能矩阵，再决定是否进入生产迁移。

## 参考资料

- [MDN WebCodecs API](https://developer.mozilla.org/en-US/docs/Web/API/WebCodecs_API)
- [W3C WebCodecs specification](https://www.w3.org/TR/webcodecs/)
- [MDN OffscreenCanvas](https://developer.mozilla.org/en-US/docs/Web/API/OffscreenCanvas)
- [MDN File System API](https://developer.mozilla.org/en-US/docs/Web/API/File_System_API)
- [MDN showOpenFilePicker](https://developer.mozilla.org/en-US/docs/Web/API/Window/showOpenFilePicker)
- [FFmpeg.wasm overview](https://ffmpegwasm.netlify.app/docs/overview)
