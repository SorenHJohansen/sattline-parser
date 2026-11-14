- **Lenient project loading.** `SattLineProject.load(..., strict=False)`,
  `ProjectLoader(strict=...)`, and `sattline project --lenient` are removed,
  together with `Diagnostic.tentative` and
  `LoadDiagnosticKind.LOAD_SKIPPED`. A missing or unparseable artifact now fails
  the load, so a project is either complete or not returned, and every
  validation finding is final.
