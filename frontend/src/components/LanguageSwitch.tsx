import { useI18n } from "../i18n/LanguageContext";

export function LanguageSwitch() {
  const { lang, setLang, t } = useI18n();
  return (
    <div className="lang-switch" role="group" aria-label={t("lang.label")}>
      <button
        className={lang === "en" ? "active" : ""}
        aria-pressed={lang === "en"}
        onClick={() => setLang("en")}
      >
        EN
      </button>
      <button
        className={lang === "vi" ? "active" : ""}
        aria-pressed={lang === "vi"}
        onClick={() => setLang("vi")}
      >
        VI
      </button>
    </div>
  );
}
