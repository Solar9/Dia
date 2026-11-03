// Interface languages beyond Polish and English (those two are complete and live in ../i18n.js).
// To add one: a file here with the strings you have (the rest falls back to English), then list it below.
import de from "./de.js";
import fr from "./fr.js";
import es from "./es.js";
import it from "./it.js";
import pt from "./pt.js";

export const EXTRA = { de, fr, es, it, pt };

export const LANGUAGE_NAMES = {
  pl: "Polski", en: "English", de: "Deutsch", fr: "Français", es: "Español", it: "Italiano", pt: "Português",
};

export const LOCALES = { pl: "pl-PL", en: "en-GB", de: "de-DE", fr: "fr-FR", es: "es-ES", it: "it-IT", pt: "pt-PT" };
