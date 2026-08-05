import type { Dictionary } from '@/lib/i18n';

export interface Slide {
  src: string;
  caption: string;
}

export function getCarouselSlides(t: Dictionary): Slide[] {
  return [
    { src: '/screens/home.png', caption: t.capHome },
    { src: '/screens/brief.png', caption: t.capBrief },
    { src: '/screens/answer.png', caption: t.capAnswer },
    { src: '/screens/admin-users.png', caption: t.capUsers },
    { src: '/screens/admin-semantic.png', caption: t.capSemantic },
  ];
}
