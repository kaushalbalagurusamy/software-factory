---
id: realtime-transport
version: 0.1.0
title: Real-time media transport
group: systems-performance
owner: sf
scope: >-
  Judges briefs that carry live audio, video or interactive state over a network: reliable in-order
  transports for live media (head-of-line blocking), playback without jitter buffering, datagrams larger than
  the path MTU, and simultaneous translation promised ahead of the input it depends on. Leaves server
  latency percentiles and cost to performance and media buffer sizing to media-pipelines.
applies_when:
  signals: [real-time audio, real-time video, realtime audio, realtime video, live audio, live video, live stream, live call, voice call, video call, conferenc, interpret, live translation, simultaneous translation, speech-to-speech, webrtc, websocket, rtp packet, srtp, udp, quic, datagram, jitter, packet loss, mtu, low-latency stream, multiplayer]
required_statements:
  - id: network-path
    statement: The brief states the network path assumptions - expected packet loss, round-trip time, jitter and MTU (or that the MTU is discovered) - the live channel must work over.
    never_out_of_scope: physics
  - id: latency-budget
    statement: The brief states an end-to-end latency budget for the live channel (for example mouth-to-ear) and how it splits across capture, processing, network, buffering and playout.
    never_out_of_scope: physics
adapters: [web_page, paper]
---

# Real-time media transport

## Principles

- TCP is a reliable, in-order byte stream (rfc9293): after a loss, already-received later data waits for the
  retransmission. QUIC limits that blocking to streams with data in the lost packet (rfc9000).
- Packet networks lose, reorder and delay packets by variable amounts; RTP timestamps and sequence numbers
  let receivers reconstruct timing, and the receiver buffer must accommodate the jitter (rfc3550).
- Losing one IP fragment loses the whole datagram; applications SHOULD NOT send UDP datagrams exceeding the
  path MTU (rfc8085). Packet counts are computed with calc.payload_mtu.
- Simultaneous translation is hard because of word-order differences; practical systems stay a stated number
  of words behind the source or anticipate (stacl-2019). Output cannot precede the input it depends on.

## Questions a sweeper asks of each claim

- Is live media carried over TCP, WebSockets or HTTP? What happens to playback at the stated loss rate?
- Is there a jitter buffer and loss concealment, and is their delay inside the latency budget?
- How large is each datagram, against what MTU (calc.payload_mtu)? Is the path MTU discovered?
- Does the brief demand output (translation, captions, decisions) faster than the input it depends on can
  arrive? Is the lag stated per language pair, with a quality metric at that lag?
- Does the brief state the network path and latency budget? If not, raise the omission.

## Severity guidance

Live media over a reliable stream on lossy access networks and translation-ahead-of-input demands answer
production-failure (high): the stated targets cannot be met. Missing jitter buffering and oversized datagrams
are principal-reject (medium), high when the product's core is live media on mobile networks. Raise to
critical only when the live channel is safety-relevant (for example emergency or clinical interpretation)
and failure would harm people.

## Not this lens

- Server-side latency percentiles, fan-out, cost: performance.
- Decoded frame memory and uncompressed rates inside a host: media-pipelines.
- Ports, descriptors and container limits: os-systems.
- Translation quality evaluation design: ml-evaluation.
