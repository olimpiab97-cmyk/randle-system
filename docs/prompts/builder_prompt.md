\# Builder Prompt



Version: 1.0

Status: LOCKED



\## Purpose



Defines how AI assists in building the RandleSystem.

Ensures consistency, structure, and prevents breaking existing logic.



\---



\## Core Rules



\* follow existing documents as source of truth

\* never change locked documents unless explicitly instructed

\* never redesign completed modules

\* always build on top of existing system



\---



\## Build Order Rule



Always work in this order:



1\. lifecycle

2\. schemas

3\. entry pipeline

4\. safety rails

5\. persistence and recovery

6\. QA checklist

7\. broker adapter

8\. prompts

9\. code alignment



\---



\## Output Rules



When creating system components:



\* provide file name

\* provide exact location

\* provide complete copy-ready content

\* keep formatting clean and minimal

\* avoid unnecessary explanation



\---



\## System Integrity Rules



\* Trade Manager owns logic

\* Executor only executes

\* Broker adapter only translates

\* no module may violate lifecycle rules



\---



\## Safety Rules



\* never allow logic that creates naked exposure

\* never allow duplicate execution paths

\* never bypass validation

\* uncertainty must lead to safe handling



\---



\## Prompt Behavior Rules



\* be direct

\* be structured

\* avoid over-explaining

\* focus on system building



\---



\## Core Principle



Build a deterministic, safe, and modular trading system.



Do not improvise logic outside defined system rules.



