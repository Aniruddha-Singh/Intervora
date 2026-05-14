import "./globals.css";

export const metadata = {
  title: "Interview Pro",
  description: "AI mock interview with smooth browser media and webcam monitoring"
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
