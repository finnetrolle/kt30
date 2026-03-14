interface LoadingStateProps {
  title?: string;
  message?: string;
}

export function LoadingState({
  title = "Loading",
  message = "Please wait while the page fetches the latest data."
}: LoadingStateProps) {
  return (
    <div className="panel">
      <div className="loading-dot" />
      <h2>{title}</h2>
      <p>{message}</p>
    </div>
  );
}
