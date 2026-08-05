import type { Dictionary } from '@/lib/i18n';

export interface HeroBar {
  value: string;
  height: number;
  month: string;
}

export interface HeroKpi {
  label: string;
  value: string;
  delta: string;
  topColor: string;
}

export interface HeroScene {
  question: string;
  title: string;
  bars: HeroBar[];
  kpis: [HeroKpi, HeroKpi];
}

/** KPI chip labels stay hardcoded English regardless of locale, matching the mockup's own convention for the revenue/margin chips. */
export function getHeroScenes(t: Dictionary): [HeroScene, HeroScene] {
  return [
    {
      question: t.demoQ,
      title: t.demoTitle,
      bars: [
        { value: '3.2', height: 52, month: 'Jan' },
        { value: '3.6', height: 62, month: 'Feb' },
        { value: '3.4', height: 57, month: 'Mar' },
        { value: '4.1', height: 74, month: 'Apr' },
        { value: '4.6', height: 88, month: 'May' },
        { value: '5.9', height: 114, month: 'Jun' },
      ],
      kpis: [
        { label: 'Revenue H1', value: '24.8M', delta: '+12%', topColor: '#6C74F0' },
        { label: 'Gross margin', value: '31%', delta: '+2.4', topColor: '#F2C94C' },
      ],
    },
    {
      question: t.demoQ2,
      title: t.demoTitle2,
      bars: [
        { value: '410', height: 66, month: 'Jan' },
        { value: '460', height: 75, month: 'Feb' },
        { value: '435', height: 70, month: 'Mar' },
        { value: '512', height: 83, month: 'Apr' },
        { value: '588', height: 95, month: 'May' },
        { value: '704', height: 114, month: 'Jun' },
      ],
      kpis: [
        { label: 'Orders H1', value: '3,109', delta: '+15%', topColor: '#6C74F0' },
        { label: 'Avg order value', value: '$187', delta: '+4%', topColor: '#F2C94C' },
      ],
    },
  ];
}
