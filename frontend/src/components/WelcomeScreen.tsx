export default function WelcomeScreen() {
  return (
    <div className="flex flex-col items-center justify-center flex-1 min-h-0 px-4">
      <div className="flex items-center gap-3 mb-4">
        <div className="h-px w-12 bg-f1-red" />
        <span className="text-[10px] uppercase tracking-[0.3em] text-f1-muted font-medium">Welcome</span>
        <div className="h-px w-12 bg-f1-red" />
      </div>
      <h1
        className="font-display text-5xl sm:text-6xl font-bold tracking-wide text-center text-white uppercase"
        style={{ transform: "skewX(-15deg)" }}
      >
        Hello, F1 Fan
      </h1>
    </div>
  );
}
