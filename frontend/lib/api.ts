export type Health = { status: "ok" };
export async function getHealth(): Promise<Health> {
  const response = await fetch("/api/health");
  if (!response.ok) throw new Error("Could not reach Shikayat. Please retry.");
  return response.json() as Promise<Health>;
}
