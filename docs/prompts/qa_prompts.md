\# QA Prompt Templates



Version: 1.0

Status: ACTIVE



\## Purpose



Provides prompts for reviewing and validating the system.



\---



\# Code Review Prompt



Review this code against:



\* trade lifecycle rules

\* safety rails

\* schemas



Check for:



\* invalid state transitions

\* missing validations

\* duplicate execution paths

\* unsafe exposure risks



Return:



\* issues found

\* severity

\* recommended fix



\---



\# Logic Validation Prompt



Analyze the following logic.



Confirm:



\* lifecycle compliance

\* correct state transitions

\* proper BE and TP1 handling

\* no duplicate triggers



Return:



\* pass or fail

\* explanation

\* corrections



\---



\# Risk Check Prompt



Evaluate whether this code can create:



\* naked positions

\* missing stops

\* duplicate fills

\* incorrect size handling



Return:



\* risk level

\* exact failure scenario

\* fix



\---



\# Recovery Validation Prompt



Check recovery logic for:



\* restart safety

\* reconciliation correctness

\* mismatch handling

\* error state behavior



Return:



\* gaps

\* risks

\* fixes



\---



\# Core Principle



QA must find problems before money is at risk.



Always assume something can break and try to find it.



