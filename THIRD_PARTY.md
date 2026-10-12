# Third-party notices

The release workflow builds a model-free runtime from the pinned
`mauri870/DLSSNR-RDNA3` source revision. Its package includes ReShade (BSD-3-Clause),
DLSS5-Feeder (MIT), MinHook (BSD-2-Clause), Dear ImGui (MIT), vort_Shader (MIT),
and the project’s own MIT-licensed code. The upstream package’s license files are
kept under `runtime/` in every release.

No NVIDIA DLL, model weight, or extracted `dlssnr.bin` file is included, downloaded,
or retained by this plugin. The UI asks the user to supply their own local source only
for local extraction at install time.
