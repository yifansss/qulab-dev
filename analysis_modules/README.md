# Project-local analysis modules

Analysis modules are import-safe, hardware-free transforms. Declare their exact inputs and outputs in both the class and YAML, put expensive initialization in `setup`, process immutable `ComputePoint` values in `process_point`, and release resources in `close`.

`show: true, save: false` creates a live-only output. `fail_policy` is one of `warn`, `skip`, or `fail`; raw acquisition and storage remain authoritative. The example in `examples/passthrough_scale.py` demonstrates the contract without defining an experiment-specific formula.

```yaml
analysis:
  live: {enabled: true, fail_policy: warn, save_outputs: true}
  modules:
    - name: scale_preview
      module: analysis_modules.examples.passthrough_scale
      class: PassthroughScale
      inputs: [source_value]
      outputs: [scaled_value]
      show: true
      args: {scale: 2.0}
```
