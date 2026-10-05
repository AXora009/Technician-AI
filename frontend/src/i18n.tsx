import { createContext, useContext, useState, useEffect, type ReactNode } from "react";

export type Lang = "en" | "zh";

const STORAGE_KEY = "tech-ai-lang";

const translations = {
  en: {
    // Tabs
    tab_diagnose: "Diagnose",
    tab_quick_ask: "Quick Ask",
    tab_library: "Library",
    tab_history: "History",

    // Chat composer
    placeholder_ask: "Ask about a spec or procedure...",
    placeholder_diagnose: "Describe what you see on the line...",

    // Mobile top bar
    open_library: "Open knowledge library",
    upload_manual: "Upload a manual",

    // Library sheet
    internal_knowledge: "Internal Knowledge",
    manuals_library: "Manuals Library",

    // Chat thread status
    status_identifying: "Identifying machine",
    status_gathering: "Gathering evidence",
    status_investigating: "Investigating",
    status_safety_hold: "Safety Hold",
    status_root_cause: "Root cause",
    status_response: "Response",
    label_confirm_safe: "Confirm safe",
    label_sources: "source(s) cited",
    label_analyzing: "Analyzing...",
    label_searching: "Searching manuals...",
    label_error: "Error — please try again.",

    // Empty states
    empty_ask_title: "Ask anything",
    empty_ask_desc: "Ask about specs, procedures, or prior fixes...",
    empty_diagnose_title: "Guided diagnosis",
    empty_diagnose_desc: "Describe the problem on the line...",

    // Ask form (desktop)
    ask_instruction: "Type the issue you ran into on the line in the box below",
    ask_enter_hint: "ENTER TO SEND · SHIFT+ENTER NEW LINE",
    btn_diagnose: "Diagnose",
    btn_quick_ask: "Quick Ask",

    // History
    loading: "Loading...",
    no_history: "No history yet.",
    label_technician: "Technician",
    label_ai: "AI",
    label_feedback: "Feedback",
    label_turns: "turns",

    // Rating widget
    rating_default_diagnose: "Rate this diagnosis",
    rating_default_ask: "Rate this answer",
    rating_labels: ["Wrong", "Partially helpful", "OK", "Good", "Spot on"],
    rating_comment_placeholder: "Enter a better solution",
    rating_submit: "Submit Rating",
    rating_saving: "Saving...",
    rating_done: "Thanks for the feedback!",

    // Sidebar / drawer
    uploaded_manuals: "Uploaded Manuals",
    add_manual: "Add a Manual",
    library: "Library",
    indexed: "indexed",
    chunks: "chunks",
    delete_manual: "Delete manual",
    delete_confirm: (name: string) => `Delete ${name} and all its chunks?`,

    // Feedback widget
    feedback_did_it_fix: "Did this fix the issue?",
    feedback_worked: "Worked",
    feedback_didnt_work: "Didn't work",
    feedback_add_note: "Add note",
    feedback_cancel: "Cancel",
    feedback_save: "Save",
    feedback_what_happened: "What actually happened on the floor?",
    feedback_what_missing: "What tip or context was missing?",
    feedback_describe: "Describe what you learned...",
    feedback_marked_worked: "Marked as worked. Thanks!",
    feedback_failed: "Failed to submit feedback.",
    btn_continue: "Continue",

    // Language picker
    lang_picker_title: "Choose your language",
    lang_picker_subtitle: "You can change this later in settings",

    // Workspace access
    ws_title: "Enter your access code",
    ws_subtitle: "Your manuals and history are private to your workspace",
    ws_placeholder: "Access code",
    ws_submit: "Enter",
    ws_invalid: "Invalid access code",
    lang_en: "English",
    lang_zh: "中文",
  },
  zh: {
    // Tabs
    tab_diagnose: "故障诊断",
    tab_quick_ask: "快速问答",
    tab_library: "知识库",
    tab_history: "历史记录",

    // Chat composer
    placeholder_ask: "询问规格、流程或操作步骤...",
    placeholder_diagnose: "描述您在生产线上看到的情况...",

    // Mobile top bar
    open_library: "打开知识库",
    upload_manual: "上传手册",

    // Library sheet
    internal_knowledge: "内部知识",
    manuals_library: "手册库",

    // Chat thread status
    status_identifying: "识别机器中",
    status_gathering: "收集信息",
    status_investigating: "分析中",
    status_safety_hold: "安全警告",
    status_root_cause: "根本原因",
    status_response: "回答",
    label_confirm_safe: "确认安全",
    label_sources: "个来源",
    label_analyzing: "分析中...",
    label_searching: "搜索手册中...",
    label_error: "出错了，请重试。",

    // Empty states
    empty_ask_title: "随时提问",
    empty_ask_desc: "询问规格、流程或历史维修记录...",
    empty_diagnose_title: "引导式诊断",
    empty_diagnose_desc: "描述生产线上的问题...",

    // Ask form (desktop)
    ask_instruction: "在下方输入您遇到的问题",
    ask_enter_hint: "回车发送 · Shift+回车换行",
    btn_diagnose: "故障诊断",
    btn_quick_ask: "快速问答",

    // History
    loading: "加载中...",
    no_history: "暂无记录。",
    label_technician: "技术员",
    label_ai: "AI",
    label_feedback: "反馈",
    label_turns: "轮",

    // Rating widget
    rating_default_diagnose: "为此次诊断评分",
    rating_default_ask: "为此次回答评分",
    rating_labels: ["错误", "部分有用", "一般", "不错", "非常准确"],
    rating_comment_placeholder: "请输入更好的解决步骤",
    rating_submit: "提交评分",
    rating_saving: "保存中...",
    rating_done: "感谢您的反馈！",

    // Sidebar / drawer
    uploaded_manuals: "已上传手册",
    add_manual: "添加手册",
    library: "知识库",
    indexed: "已索引",
    chunks: "段",
    delete_manual: "删除手册",
    delete_confirm: (name: string) => `删除 ${name} 及其所有内容？`,

    // Feedback widget
    feedback_did_it_fix: "这个方法解决问题了吗？",
    feedback_worked: "解决了",
    feedback_didnt_work: "没解决",
    feedback_add_note: "添加备注",
    feedback_cancel: "取消",
    feedback_save: "保存",
    feedback_what_happened: "现场实际发生了什么？",
    feedback_what_missing: "缺少了哪些提示或背景信息？",
    feedback_describe: "描述您学到的内容...",
    feedback_marked_worked: "已标记为有效，谢谢！",
    feedback_failed: "提交反馈失败。",
    btn_continue: "继续",

    // Language picker
    lang_picker_title: "选择您的语言",
    lang_picker_subtitle: "您可以稍后在设置中更改",

    // Workspace access
    ws_title: "请输入访问码",
    ws_subtitle: "您的手册和记录只在您自己的空间中可见",
    ws_placeholder: "访问码",
    ws_submit: "进入",
    ws_invalid: "访问码无效",
    lang_en: "English",
    lang_zh: "中文",
  },
} as const;

type Translations = (typeof translations)["en"];

interface LangContextValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: Translations;
}

const LangContext = createContext<LangContextValue | null>(null);

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang | null>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === "en" || stored === "zh" ? stored : null;
  });

  const setLang = (l: Lang) => {
    localStorage.setItem(STORAGE_KEY, l);
    setLangState(l);
  };

  const t = translations[lang ?? "en"] as Translations;

  return (
    <LangContext.Provider value={{ lang: lang ?? "en", setLang, t }}>
      {lang === null && <LangPicker onSelect={setLang} t={translations.en} />}
      {lang !== null && children}
    </LangContext.Provider>
  );
}

export function useLang() {
  const ctx = useContext(LangContext);
  if (!ctx) throw new Error("useLang must be used inside LangProvider");
  return ctx;
}

function LangPicker({ onSelect, t }: { onSelect: (l: Lang) => void; t: Translations }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background">
      <div className="w-72 rounded-lg border border-border bg-card p-6 shadow-lg text-center space-y-6">
        <div>
          <h2 className="text-base font-semibold">{t.lang_picker_title}</h2>
          <p className="text-xs text-muted-foreground mt-1">{t.lang_picker_subtitle}</p>
        </div>
        <div className="flex flex-col gap-3">
          <button
            onClick={() => onSelect("en")}
            className="w-full rounded-md border border-border py-3 text-sm font-medium hover:bg-muted transition-colors"
          >
            🇺🇸 English
          </button>
          <button
            onClick={() => onSelect("zh")}
            className="w-full rounded-md border border-border py-3 text-sm font-medium hover:bg-muted transition-colors"
          >
            🇨🇳 中文
          </button>
        </div>
      </div>
    </div>
  );
}
