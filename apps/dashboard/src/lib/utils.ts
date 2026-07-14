import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** shadcn/ui convention — class merging helper used by copied-in components. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
