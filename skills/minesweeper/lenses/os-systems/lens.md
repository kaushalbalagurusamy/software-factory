---
id: os-systems
version: 0.1.0
title: Operating system resource limits
group: systems-performance
owner: sf
scope: >-
  Judges brief claims that, built literally, run a host out of kernel-managed resources: ephemeral ports,
  file descriptors, threads and processes, and container memory (including page cache) before the OOM killer
  acts. Leaves latency percentiles, queueing and cost to performance, media buffer sizing to media-pipelines,
  and network-path behaviour to realtime-transport.
applies_when:
  signals: [requests per second, rps, connections, connection per, new connection, connection pool, keep-alive, webhook, socket, file descriptor, open files, ulimit, container, memory limit, out of memory, oom, serverless, kubernetes, worker process, thread per, new thread, spawn, fork, page cache, mmap, concurrent users, concurrent clients, websocket]
required_statements:
  - id: memory-budget-per-worker
    statement: The brief states a memory budget per worker or container and the peak input size and concurrency it must hold.
    never_out_of_scope: physics
  - id: concurrency-model
    statement: The brief states the concurrency model (pooled connections, bounded worker pool or event loop) and the peak concurrent connections, threads and open files per host.
    never_out_of_scope: physics
adapters: [web_page]
---

# Operating system resource limits

## Principles

- The local port for an outbound connection comes from the ephemeral range (Linux default 32768-60999); when
  all are in use, connect() fails with EADDRNOTAVAIL (kernel-ip-sysctl, man-connect2).
- TIME-WAIT limits the rate of connection reuse; RFC 9293 takes MSL as 2 minutes (rfc9293). The actual
  TIME-WAIT length on a host is a kernel setting to read, not to recall.
- RLIMIT_NOFILE bounds descriptors per process; exceeding it yields EMFILE, and sockets, pipes and files all
  count (man-getrlimit2).
- Thread creation fails with EAGAIN at RLIMIT_NPROC or the system thread limit; each thread's default stack
  size follows RLIMIT_STACK (man-pthread-create3).
- A cgroup reaching memory.max that cannot reclaim invokes the OOM killer in that cgroup; the victim is
  scored against that configured limit (kernel-cgroup-v2, man-proc-oom).
- Page cache is charged to the cgroup alongside anonymous memory (kernel-cgroup-v2).

## Questions a sweeper asks of each claim

- What is the peak rate of new outbound connections, and are they pooled and kept alive? Rate x TIME-WAIT
  against the ephemeral range per destination.
- How many sockets, files and pipes can be open at once per process, and what is RLIMIT_NOFILE in the target
  deployment?
- Does the design create a thread or process per request, connection or job? What bounds it?
- What is the memory limit per worker, the peak resident memory per request (calc.memory for buffers), and
  the admitted concurrency? Does the arithmetic fit?
- Does the brief rely on the file cache or memory-mapped files being "free"?
- Does the brief state the memory budget and concurrency model at all? If not, raise the omission.

## Severity guidance

Port, descriptor, thread and memory exhaustion usually answer yes to production-failure (high): the brief's
own load makes the host stop serving. Raise to critical only if the failure harms users or safety (for
example a safety-relevant controller stops). Page-cache assumptions are usually principal-reject (medium)
unless the brief's working set clearly exceeds the limit. Lower when the brief already states pooling,
bounded workers and a measured memory budget.

## Not this lens

- Latency percentiles, fan-out, queue bounds and cloud cost: performance.
- Decoded image and video buffer sizes, bit depth: media-pipelines.
- Transport choice, jitter, MTU on the network path: realtime-transport.
- Database connection semantics and isolation: databases.
