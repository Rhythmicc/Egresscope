export function PageRenderer({ page, device, devicePage, pages }) {
  if (device) return devicePage;
  return pages[page] || pages.dashboard;
}
