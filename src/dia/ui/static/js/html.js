// htm bound to Preact's h: the `html` template tag every component uses.
import { h } from "preact";
import htm from "htm";

export const html = htm.bind(h);
