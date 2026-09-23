Extract evidence passages from the supplied source for the author's thesis.

The intent JSON contains the author's thesis and must-use passages. Return passages that support, complicate, or contradict the thesis. Quotes must be exact substrings copied from the source text; never reconstruct, translate, or silently normalize a quote. Include a locator, a concise gloss, and relevance from 0 through 3. Return only passages useful to the author's argument.
