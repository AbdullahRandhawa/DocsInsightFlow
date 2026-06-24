export function Spinner({ size = "default", className = "" }) {
  const sizeClass = size === "sm" ? "spinner-sm" : size === "lg" ? "spinner-lg" : "";
  return <div className={`spinner ${sizeClass} ${className}`} />;
}
