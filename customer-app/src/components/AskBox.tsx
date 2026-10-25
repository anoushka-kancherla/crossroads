import { StatusMessage } from "../brand/StatusMessage";
import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, type PathsInputs } from "../api/client";

const MAX = 300;

type Props = { customerId: string; inputs: PathsInputs };

/** "Ask about your options" (FR-041). The answer is written by the model from the engine's own figures and
 *  shown only after the server has checked every number in it. When it can't be answered reliably the screen
 *  says so and shows nothing from the model. The slider settings travel with the question, so the answer
 *  matches what is on screen. */
export function AskBox({ customerId, inputs }: Props) {
  const [question, setQuestion] = useState("");
  const settings = JSON.stringify(inputs);
  const [answeredFor, setAnsweredFor] = useState<string | null>(null);
  const ask = useMutation({
    mutationFn: () => api.ask(customerId, { ...inputs, question: question.trim() }),
    onSuccess: () => setAnsweredFor(settings),
  });

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (question.trim()) ask.mutate();
  };

  return (
    <section className="panel" aria-labelledby="ask-title">
      <h2 id="ask-title">Ask about your options</h2>
      <form onSubmit={submit}>
        <label htmlFor="ask-question">Your question</label>
        <textarea
          id="ask-question"
          rows={2}
          maxLength={MAX}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="For example: what if I keep the car longer?"
        />
        <p className="basis">
          {question.length} of {MAX} characters. Answers use only the figures on this page.
        </p>
        <button className="secondary" type="submit" disabled={ask.isPending || !question.trim()}>
          {ask.isPending ? "Thinking…" : "Ask"}
        </button>
      </form>
      <div aria-live="polite">
        {ask.isPending && <p role="status">Thinking…</p>}
        {ask.isError && (
          <StatusMessage variant="critical" label="Error">
            {ask.error.message}
          </StatusMessage>
        )}
        {ask.isSuccess &&
          (ask.data.answer ? (
            <>
              <p className="answer">{ask.data.answer}</p>
              <p className="basis">
                <StatusMessage variant="positive" label="Numbers verified" />{" "}
                {answeredFor !== settings && "This answer was for your earlier slider settings."}
              </p>
            </>
          ) : (
            <div role="status">
              <StatusMessage variant="neutral" label="No answer">
                {ask.data.message ?? "I can't answer that reliably."}
              </StatusMessage>
            </div>
          ))}
      </div>
    </section>
  );
}
