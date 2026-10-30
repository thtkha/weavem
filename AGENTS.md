# Working in Weavem

Follow the repository's [context and handoff policy](docs/maintainers/context-policy.md).
Important decisions and continuation context must not exist only in a chat,
agent message, local cache, or ignored artifact. Update the relevant tracked
instructions/records before handing off or claiming completion.

Start with the [documentation audience map](docs/index.md). Current usage,
maintainer instructions, and historical project evidence serve different purposes.
Do not promote unreleased or branch-only behavior into the released user manual.

## Agent-led execution

Keep the main conversation available for decisions and progress. Delegate bounded
implementation, investigation and long verification runs to native agents when
available. The leader coordinates ownership/interfaces, reviews and integrates
results, and performs direct work only when it is the appropriate narrow lane.
Do not invent background activity: report actual agent state and verification.
