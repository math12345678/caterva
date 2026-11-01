/* The element the MuleRun chapters live in on the merged site.

   On their own page these modules appended the mode dock, the live region
   and the inspector to <body>. Merged, their stylesheet is scoped under
   `.mule`, so anything outside that element would render unstyled; they
   attach here instead. Defaults to <body> so the modules still work alone. */
let host = null;

export function setHost(el) { host = el; }
export function getHost() { return host || document.body; }
