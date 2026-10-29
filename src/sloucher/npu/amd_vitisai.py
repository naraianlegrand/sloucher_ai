"""AMD Ryzen AI NPU backend (Phoenix / Hawk Point), through the Vitis AI execution provider.

Runs inside AMD's Ryzen AI Python. Lessons from the lab, kept here:
- Phoenix / Hawk Point needs the legacy X1 target plus an NPU binary (xclbin). 4x4 uses
  4 of the NPU's 5 columns; 1x4 uses 1, which leaves room for Windows Studio Effects.
- ONNX Runtime's thread pool busy-waits by default: it burned ~7 CPU cores and made
  inference 8x slower at 2 fps. Spinning off + 1 thread fixes it.
- The provider reports where the model runs ("Actually running on NPU") from native code,
  straight to stdout: the app reads it from this process's output. There is no CPU fallback:
  only the Vitis AI provider is requested.
"""


def open_session(model, xclbin):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.add_session_config_entry("session.intra_op.allow_spinning", "0")
    so.add_session_config_entry("session.inter_op.allow_spinning", "0")
    so.intra_op_num_threads = 1
    so.inter_op_num_threads = 1
    return ort.InferenceSession(model, so, providers=["VitisAIExecutionProvider"],
                                provider_options=[{"target": "X1", "xclbin": xclbin}])
