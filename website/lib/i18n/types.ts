export type Locale = 'en' | 'he';

export interface Dictionary {
  navProduct: string;
  navHow: string;
  navCustomers: string;
  navPricing: string;
  cta: string;
  secondary: string;
  badge: string;
  h1: string;
  sub: string;
  demoLabel: string;
  demoQ: string;
  demoTitle: string;
  logosLabel: string;
  featKicker: string;
  featTitle: string;
  f1Title: string;
  f1Body: string;
  f2Title: string;
  f2Body: string;
  f3Title: string;
  f3Body: string;
  proKicker: string;
  proTitle: string;
  proSub: string;
  homeGreeting: string;
  homeSub: string;
  a1Tag: string;
  a1Text: string;
  a1Time: string;
  a2Tag: string;
  a2Text: string;
  a2Time: string;
  a3Tag: string;
  a3Text: string;
  a3Time: string;
  howKicker: string;
  howTitle: string;
  s1Title: string;
  s1Body: string;
  s2Title: string;
  s2Body: string;
  s3Title: string;
  s3Body: string;
  quoteKicker: string;
  quoteTitle: string;
  priceTitle: string;
  priceSub: string;
  perMonth: string;
  popular: string;
  custom: string;
  talkSales: string;
  tier1Name: string;
  tier1Sub: string;
  tier2Name: string;
  tier2Sub: string;
  tier3Name: string;
  tier3Sub: string;
  priceNote: string;
  ctaTitle: string;
  ctaSub: string;
  formTitle: string;
  fName: string;
  fCompany: string;
  fEmail: string;
  fMsg: string;
  formNote: string;
  footTag: string;
  footPrivacy: string;
  footTerms: string;
}

export interface TierPoints {
  t1: string[];
  t2: string[];
  t3: string[];
}

export interface Quote {
  name: string;
  role: string;
  text: string;
  init: string;
  tint: string;
  color: string;
}
