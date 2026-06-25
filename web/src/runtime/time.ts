export function toIsoUtc(value: string | Date): string {
  const date = value instanceof Date ? value : new Date(value);
  return date.toISOString();
}

export function addSeconds(value: string, seconds: number): string {
  return new Date(new Date(value).getTime() + seconds * 1000).toISOString();
}

export function secondsBetween(start: string, end: string): number {
  return (new Date(end).getTime() - new Date(start).getTime()) / 1000;
}

export function maxIso(left: string, right: string): string {
  return new Date(left).getTime() >= new Date(right).getTime() ? left : right;
}

export function minIso(left: string, right: string): string {
  return new Date(left).getTime() <= new Date(right).getTime() ? left : right;
}
