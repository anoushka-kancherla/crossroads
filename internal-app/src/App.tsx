import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api/client";
import { QueryState } from "./components/QueryState";
import Login from "./routes/Login";
import Portfolio from "./routes/Portfolio";

// This app has no link to the customer app (FR-023). Nothing but sign-in renders until the server
// confirms a staff session, and no portfolio request is made before then.
export default function App() {
  const qc = useQueryClient();
  const session = useQuery({ queryKey: ["session"], queryFn: api.session, retry: false });
  const signOut = useMutation({
    mutationFn: api.logout,
    onSettled: () => {
      qc.removeQueries({ queryKey: ["portfolio"] });
      qc.setQueryData(["session"], null);
    },
  });

  const user = session.data?.user;
  return (
    <>
      <header className="topbar">
        <div>
          <strong>Crossroads Internal</strong>
          <div className="brand-sub">Toyota Financial Services · staff only</div>
        </div>
        {user && (
          <div className="who">
            <span>Signed in as {user}</span>
            <button className="secondary" onClick={() => signOut.mutate()} disabled={signOut.isPending}>
              Sign out
            </button>
          </div>
        )}
      </header>
      <main>
        <QueryState status={session.status} error={session.error} data={session.data}>
          {(s) => (
            <Routes>
              <Route path="/login" element={s ? <Navigate to="/" replace /> : <Login />} />
              <Route path="/" element={s ? <Portfolio /> : <Navigate to="/login" replace />} />
            </Routes>
          )}
        </QueryState>
      </main>
    </>
  );
}
