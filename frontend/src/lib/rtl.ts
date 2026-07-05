// Decide a turn's text direction from the question's language (mirrors the
// Streamlit app's rule): any Hebrew -> the whole turn renders right-to-left.
const HEBREW = /[֐-׿יִ-ﭏ]/;

export function isRtl(text: string): boolean {
  return !!text && HEBREW.test(text);
}

export function dirOf(text: string): "rtl" | "ltr" {
  return isRtl(text) ? "rtl" : "ltr";
}
