---
id: media-pipelines
version: 0.1.0
title: Image and video pipeline physics
group: systems-performance
owner: sf
scope: >-
  Judges briefs that decode, transform or move images and video: decoded-frame memory against worker limits,
  precision lost by early 8-bit quantization of HDR or high-bit-depth input, and uncompressed data rates
  between stages. Leaves generic container limits to os-systems, latency and cost to performance, and network
  transport of live media to realtime-transport.
applies_when:
  signals: [image processing, image pipeline, photos, photo upload, raw photo, raw image, bracket, exposure fusion, exposures, hdr, tone map, video, frames per, video frame, fps, frame rate, 4k, 8k, megapixel, high-resolution, high resolution, transcode, codec, render video, video render, bit depth, 10-bit, 12-bit, colour space, color space, camera]
required_statements:
  - id: media-format
    statement: The brief states the media parameters the pipeline must handle - maximum resolution, frame count or frame rate, bit depth, colour space and transfer function - for input and output.
    never_out_of_scope: physics
  - id: memory-budget-per-worker
    statement: The brief states the memory budget per worker and how many media requests a worker processes at once.
    never_out_of_scope: physics
adapters: [web_page]
---

# Image and video pipeline physics

## Principles

- Decoded memory = frames x width x height x channels x bytes per channel, per concurrent request, before
  intermediates (calc.memory). When a container's usage reaches memory.max and cannot be reclaimed, the OOM
  killer runs in that cgroup (kernel-cgroup-v2).
- Uncompressed rate = width x height x channels x bytes per channel x fps on every link and copy
  (calc.bandwidth). Link and bus capacities are measured, not recalled.
- HDR signals are specified at 10 or 12 bits with PQ or HLG transfer functions (itu-bt2100, unverified until
  quoted); precision discarded early cannot be recovered by later stages.
- Figures such as "3.84 GB per burst" or "3.98 GB/s for 4K60 half-float RGBA" are arithmetic from stated
  parameters; recompute them with calc for the brief's own numbers.

## Questions a sweeper asks of each claim

- What is the maximum resolution, frame count, channels and working precision? What does calc.memory give
  per request, and times the admitted concurrency?
- What is the worker memory limit? Is there an admission bound on concurrent media jobs?
- Does any stage convert to 8-bit or to an SDR transfer function before merge, grading or tone mapping?
- Are decoded frames passed between processes or hosts? What does calc.bandwidth give, against which
  measured link?
- Does the brief state the media format and memory budget at all? If not, raise the omission.

## Severity guidance

Decoded memory over the worker limit at the brief's own concurrency answers production-failure (high).
Precision loss that defeats the product's stated purpose (an HDR product producing clipped output) is high;
precision loss in a non-HDR thumbnail path is low. Uncompressed rates beyond link capacity are high when real
time is required, medium for batch.

## Not this lens

- Container and kernel limits in general: os-systems.
- Latency percentiles, queues and transfer cost of media delivery: performance.
- Live media over the network (transport, jitter, MTU): realtime-transport.
- Codec licensing and patent pools: licensing.
