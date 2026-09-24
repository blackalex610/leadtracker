import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { KeyRoundIcon } from "lucide-react";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, errorMessage } from "@/lib/api";
import { keys } from "@/lib/queries";

const schema = z.object({ token: z.string().trim().min(10, "Paste your access token") });

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
    <div className="grid min-h-dvh place-items-center bg-muted/30 p-4">
      <Card className="w-full max-w-sm">
        <CardContent className="grid gap-4 py-6">
          <div>
            <h1 className="text-base font-semibold">Lead Tracker</h1>
            <p className="text-xs text-muted-foreground">Sign in with the access token your admin gave you.</p>
          </div>
          <form className="grid gap-3" onSubmit={form.handleSubmit((v) => login.mutate(v.token))} noValidate>
            <div className="grid gap-1">
              <Label htmlFor="token">Access token</Label>
              <Input id="token" type="password" autoComplete="current-password" autoFocus {...form.register("token")} />
              {form.formState.errors.token && <p className="text-xs text-bad">{form.formState.errors.token.message}</p>}
              {login.error && <p className="text-xs text-bad" role="alert">{errorMessage(login.error)}</p>}
            </div>
            <Button type="submit" disabled={login.isPending}>
              <KeyRoundIcon /> {login.isPending ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
