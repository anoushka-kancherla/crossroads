import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api } from "../api/client";

/** Staff sign-in. A failed attempt shows one generic message, whatever was wrong (FR-025). */
export default function Login() {
  const qc = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  const signIn = useMutation({
    mutationFn: () => api.login(username, password),
    // The session query then reports who signed in and the dashboard takes over.
    onSuccess: () => qc.invalidateQueries({ queryKey: ["session"] }),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    signIn.mutate();
  };

  return (
    <form className="login" onSubmit={submit} aria-label="Staff sign-in">
      <h1>Staff sign-in</h1>
      <label>
        Username
        <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required />
      </label>
      <label>
        Password
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />
      </label>
      {signIn.isError && <p role="alert">{signIn.error.message}</p>}
      <button className="primary" type="submit" disabled={signIn.isPending}>
        {signIn.isPending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
