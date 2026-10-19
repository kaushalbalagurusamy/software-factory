---
id: demo-login
title: Sign in with email and password
priority: P1
depends_on: []
status: draft
source_requirement_ids: [R-01, R-02]
---

## Why

Visitors cannot reach their saved work until they can prove who they are.

## UX stories

### US-1 Sign in
As a returning customer I can sign in with my email and password so that I see my saved work.
Device: iPhone 390 px wide, Safari, one-handed, on a mobile connection.

### US-2 Understand a failed sign-in
As a returning customer I can see why sign-in failed so that I can fix my entry without guessing.
Context: desktop browser, after typing the wrong password.

## What Changes

A sign-in form and a session cookie.

## Out of scope

Password reset and social sign-in.

## Impact

New route /login; no change to existing routes.
