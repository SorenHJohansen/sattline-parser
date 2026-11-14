- **Project scope fixes.** A datecode conflict now names only the visible
  versions that differ from the program's own, so a closure holding versions 1
  and 2 no longer hides the conflict on a program that declares 1. Invoked
  validation resolves a module-type reference inside the referencing program's
  dependency closure, so a same-named type in an unrelated library is no longer
  validated. Module-type recursion is rejected at the first cycle found instead
  of enumerating every elementary cycle.
