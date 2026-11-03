import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, errorMessage } from "@/lib/api";
import { keys } from "@/lib/queries";

const schema = z.object({ token: z.string().trim().min(1, "Enter the password") });

export function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const client = useQueryClient();
  const form = useForm<z.infer<typeof schema>>({ resolver: zodResolver(schema), defaultValues: { token: "" } });
  const login = useMutation({
    mutationFn: (token: string) => api.login(token),
    onSuccess: (data) => {
      client.setQueryData(keys.me, data);
      const next = params.get("next");
      navigate(next && next.startsWith("/") && !next.startsWith("//") ? next : "/", { replace: true });
    },
  });
  return (
    <div className="grid min-h-dvh place-items-center bg-brand-ink p-4 text-white">
      <div className="grid w-full max-w-xs gap-8">
        <div className="grid justify-items-center gap-3">
          <img src="/kov4-wordmark.png" alt="KOV4" width={146} height={61} className="h-auto w-56" />
          <h1 className="text-sm font-medium text-white/60">Lead Tracker</h1>
        </div>
        <form className="grid gap-3" onSubmit={form.handleSubmit((v) => login.mutate(v.token))} noValidate>
          <div className="grid gap-1.5">
            <Label htmlFor="token" className="text-white/80">
              Password
            </Label>
            <Input
              id="token"
              type="password"
              autoComplete="current-password"
              autoFocus
              className="h-10 border-white/15 bg-white/5 text-base text-white focus-visible:border-brand focus-visible:ring-brand/40"
              {...form.register("token")}
            />
            {form.formState.errors.token && <p className="text-xs text-[#ff6b76]">{form.formState.errors.token.message}</p>}
            {login.error && (
              <p className="text-xs text-[#ff6b76]" role="alert">
                {errorMessage(login.error)}
              </p>
            )}
          </div>
          <Button
            type="submit"
            disabled={login.isPending}
            className="h-10 bg-brand text-sm font-semibold text-brand-foreground hover:bg-brand-hover"
          >
            {login.isPending ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </div>
    </div>
  );
}
