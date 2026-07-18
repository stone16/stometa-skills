# Dead link fixture

This live pointer is fine: @./front_good.md

This pointer is dead and MUST be flagged (LINK-01): @./nonexistent.md

The following dead pointers MUST be skipped by the failure-mode guards:

```
A dead pointer inside a fenced code block: @./fenced_dead.md
```

# A dead pointer in an ATX heading must be checked: @./hash_dead.md

<!-- A dead pointer in an HTML comment: @./html_dead.md -->

<!--
A dead pointer inside a MULTI-LINE HTML comment: @./multiline_dead.md
still inside the comment here
-->

After the multi-line comment closes, normal text resumes.
