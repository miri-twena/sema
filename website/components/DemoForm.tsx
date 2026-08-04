'use client';

import { useRef } from 'react';
import type { Dictionary } from '@/lib/i18n';

// TODO: replace the mailto: handoff with a real POST to the lead-capture endpoint once one exists.
const SALES_EMAIL = 'hello@sema.example';

export default function DemoForm({ t }: { t: Dictionary }) {
  const formRef = useRef<HTMLFormElement>(null);

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const data = new FormData(e.currentTarget);
    const name = data.get('name')?.toString() ?? '';
    const company = data.get('company')?.toString() ?? '';
    const email = data.get('email')?.toString() ?? '';
    const message = data.get('message')?.toString() ?? '';
    const subject = encodeURIComponent(`${t.formTitle}: ${company || name}`);
    const body = encodeURIComponent(
      `${t.fName}: ${name}\n${t.fCompany}: ${company}\n${t.fEmail}: ${email}\n\n${message}`,
    );
    window.location.href = `mailto:${SALES_EMAIL}?subject=${subject}&body=${body}`;
  }

  return (
    <form
      ref={formRef}
      onSubmit={handleSubmit}
      className="flex flex-col gap-4 rounded-card-lg bg-white px-7 py-[30px]"
    >
      <h3 className="m-0 text-xl font-extrabold">{t.formTitle}</h3>
      <div className="grid grid-cols-2 gap-3">
        <input
          name="name"
          required
          placeholder={t.fName}
          className="rounded-[10px] border border-border px-3.5 py-3 text-sm [outline-color:#6C74F0] focus:outline"
        />
        <input
          name="company"
          placeholder={t.fCompany}
          className="rounded-[10px] border border-border px-3.5 py-3 text-sm [outline-color:#6C74F0] focus:outline"
        />
      </div>
      <input
        name="email"
        type="email"
        required
        placeholder={t.fEmail}
        className="rounded-[10px] border border-border px-3.5 py-3 text-sm [outline-color:#6C74F0] focus:outline"
      />
      <textarea
        name="message"
        rows={3}
        placeholder={t.fMsg}
        className="resize-y rounded-[10px] border border-border px-3.5 py-3 text-sm [outline-color:#6C74F0] focus:outline"
      />
      <button
        type="submit"
        className="rounded-[11px] bg-brand py-3.5 text-center text-[15px] font-bold text-white transition-colors duration-150 hover:bg-brand-hover"
      >
        {t.cta}
      </button>
      <span className="text-center text-xs text-text-faint">{t.formNote}</span>
    </form>
  );
}
