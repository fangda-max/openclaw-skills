# Checkstyle Tool Bundles

This directory stores Checkstyle bundles used by the Java style entropy analyzer.

## Version Policy

- Runtime JDK `1.8` uses `jdk8`.
- Runtime JDK greater than `1.8` uses `jdk17`.

The analyzer should still allow users to override the jar, config, and suppression
paths from `entropy.config.toml`.

## Layout

- `jdk8/`: Java 8 compatible Checkstyle bundle.
- `jdk17/`: Java 17+ compatible Checkstyle bundle placeholder.

