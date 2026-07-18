import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { translations } from "./translations";
import type { Lang, Narrative, TranslationKey } from "./translations";

const STORAGE_KEY = "greenmpc.lang";

function interpolate(template: string, params?: Record<string, string | number>): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name) => (name in params ? String(params[name]) : match));
}

function translate(lang: Lang, key: string, params?: Record<string, string | number>): string {
  const table = translations[lang] as Record<string, string>;
  const fallback = translations.en as Record<string, string>;
  const template = table[key] ?? fallback[key] ?? key;
  return interpolate(template, params);
}

export interface I18n {
  lang: Lang;
  setLang: (lang: Lang) => void;
  toggle: () => void;
  /** Translate a catalog key, with optional {name} interpolation. */
  t: (key: TranslationKey | string, params?: Record<string, string | number>) => string;
  /** Resolve a deferred narrative (key + params, plus optional nested scenario label). */
  tn: (narrative: Narrative | null | undefined) => string;
}

function makeI18n(lang: Lang, setLang: (lang: Lang) => void): I18n {
  const t = (key: TranslationKey | string, params?: Record<string, string | number>) => translate(lang, key, params);
  const tn = (narrative: Narrative | null | undefined) => {
    if (!narrative) return "";
    const params = { ...(narrative.params ?? {}) };
    if (narrative.scenarioId) params.label = t(`scenario.${narrative.scenarioId}`);
    return t(narrative.key, params);
  };
  return { lang, setLang, toggle: () => setLang(lang === "en" ? "vi" : "en"), t, tn };
}

// Default context is a fully-functional English translator, so components
// rendered outside a provider (e.g. unit tests) still render correctly.
const LanguageContext = createContext<I18n>(makeI18n("en", () => undefined));

function readInitialLang(): Lang {
  if (typeof window === "undefined") return "en";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === "vi" ? "vi" : "en";
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readInitialLang);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, next);
  }, []);

  useEffect(() => {
    if (typeof document !== "undefined") document.documentElement.lang = lang;
  }, [lang]);

  const value = useMemo(() => makeI18n(lang, setLang), [lang, setLang]);
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useI18n(): I18n {
  return useContext(LanguageContext);
}
