declare module 'next' {
  export type NextConfig = any;
  export type Metadata = any;
  const next: any;
  export default next;
}

declare module 'next/font/google' {
  export function Inter(options?: any): {
    className: string;
    style: { fontFamily: string; fontWeight?: number; fontStyle?: string };
  };
  export function Geist(options?: any): {
    className: string;
    variable: string;
    style: { fontFamily: string; fontWeight?: number; fontStyle?: string };
  };
  export function Geist_Mono(options?: any): {
    className: string;
    variable: string;
    style: { fontFamily: string; fontWeight?: number; fontStyle?: string };
  };
}
