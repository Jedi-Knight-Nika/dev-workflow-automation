# Optional Gource renderer

The application loads this frame only when the operator selects **Open Gource replay**. `bridge.js` passes a bounded metadata-only log to the engine and accepts messages only from the same-origin parent. The parent removes the frame on failure or close. Browser assets are self-hosted; the upstream demo UI, repository cloning, authentication and proxy are not included.

Engine: [Posnet/gource-web](https://github.com/Posnet/gource-web), commit `2ad10b412c2c2918046dbe2f4187ad9b880f9686`.

`vendor/gource-web.js`, `.wasm` and `.data` are the unmodified upstream `dist` artifacts at that revision. `vendor/COPYING` contains the upstream license. `vendor/source.tar.gz` contains the corresponding repository source at that revision, including its build configuration. Both license and source are linked from the viewer. `vendor/manifest.json` records SHA-256 hashes for every supplied artifact.

To update, review a specific upstream commit, replace all three runtime artifacts together, include that revision's source archive and license, and regenerate the manifest hashes. Follow the pinned source's build instructions if rebuilding. Run the activity browser tests with the actual local assets, including initialization, pause, failure, return and resource disposal. Do not replace the bridge with the upstream hosted demo or introduce runtime CDN dependencies.

Gource playback is independent of the Canvas timeline. The frame requires WebGL2 and WebAssembly; Canvas and native log export remain available if the engine cannot start. The main loop pauses when the tab is hidden. No renderer runs before the viewer is explicitly opened.
