---
id: troubleshooting-a-custom-tool-times-out-or-errors-check--4
title: A custom tool times out or errors
route: "/docs#troubleshooting"
group: Help
audience: user
source: docs
tags: [faq, troubleshooting, help]
questions:
  - "A custom tool times out or errors: check the Test dialog first. Tools run sandboxed with public HTTP(S) access (up to 25 network calls and ~90s per run, 180s while testing); heavy ML libraries and private hosts are blocked. Use Storage for files and Code Interpreter for heavy calculations."
---

## A custom tool times out or errors

A custom tool times out or errors: check the Test dialog first. Tools run sandboxed with public HTTP(S) access (up to 25 network calls and ~90s per run, 180s while testing); heavy ML libraries and private hosts are blocked. Use Storage for files and Code Interpreter for heavy calculations.
