import { ButtonItem, DropdownItem, Field, PanelSection, PanelSectionRow, SliderField, ToggleField, staticClasses } from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import { useEffect, useMemo, useState } from "react";
import { FaWandMagicSparkles } from "react-icons/fa6";

type Target = { exe: string; directory: string; architecture: "x86" | "x86_64" };
type Game = { appid: string; name: string; install_dir: string; targets: Target[]; installed: boolean };
type Status = { installed: boolean; integrity?: boolean; settings?: Record<string, string>; manifest?: { directory: string } };
const listGames = callable<[], { games: Game[] }>("list_games");
const install = callable<[appid: string, exe: string, model: string, backup: boolean, antiCheatAcknowledged: boolean], { message: string; launch_option: string }>("install");
const remove = callable<[appid: string], { message: string; preserved: string[] }>("remove");
const getStatus = callable<[appid: string], Status>("get_status");
const saveSettings = callable<[appid: string, settings: Record<string, string>], { settings: Record<string, string> }>("save_settings");

function Content() {
  const [games, setGames] = useState<Game[]>([]);
  const [appid, setAppid] = useState("");
  const [exe, setExe] = useState("");
  const [model, setModel] = useState("");
  const [replace, setReplace] = useState(false);
  const [antiCheatAcknowledged, setAntiCheatAcknowledged] = useState(false);
  const [status, setStatus] = useState<Status>({ installed: false });
  const [message, setMessage] = useState("Game must be closed before installing or removing.");
  const selected = useMemo(() => games.find((game) => game.appid === appid), [games, appid]);

  const refresh = async () => {
    const result = await listGames(); setGames(result.games);
    const next = appid && result.games.some((game) => game.appid === appid) ? appid : result.games[0]?.appid || "";
    setAppid(next);
  };
  useEffect(() => { void refresh().catch((error) => setMessage(String(error))); }, []);
  useEffect(() => {
    if (!selected) { setExe(""); return; }
    setExe((current) => selected.targets.some((target) => target.exe === current) ? current : selected.targets[0]?.exe || "");
    void getStatus(selected.appid).then(setStatus).catch((error) => setMessage(String(error)));
  }, [selected?.appid]);
  const toastError = (error: unknown) => { const text = error instanceof Error ? error.message : String(error); setMessage(text); toaster.toast({ title: "DLSSNR Manager", body: text }); };
  const apply = async () => { try { if (!appid || !exe || !model) throw new Error("Choose a game EXE and your local nvngx_dlssnr.dll/zip."); const result = await install(appid, exe, model, replace, antiCheatAcknowledged); setMessage(`${result.message} Launch option: ${result.launch_option}`); setStatus(await getStatus(appid)); } catch (error) { toastError(error); } };
  const uninstall = async () => { try { const result = await remove(appid); setMessage(result.message + (result.preserved.length ? " Modified files were preserved." : "")); setStatus(await getStatus(appid)); } catch (error) { toastError(error); } };
  const update = async (values: Record<string, string>) => { try { const result = await saveSettings(appid, values); setStatus((current) => ({ ...current, settings: result.settings })); setMessage("Saved. Settings apply on the next game launch."); } catch (error) { toastError(error); } };
  const settings = status.settings || {};
  return <PanelSection title="DLSSNR Manager">
    <PanelSectionRow><Field>{message}</Field></PanelSectionRow>
    <PanelSectionRow><DropdownItem rgOptions={games.map((game) => ({ label: game.name, data: game.appid }))} selectedOption={appid} onChange={(option) => setAppid(String(option.data))}>Installed Steam game</DropdownItem></PanelSectionRow>
    <PanelSectionRow><DropdownItem rgOptions={(selected?.targets || []).map((target) => ({ label: `${target.exe.split("/").pop()} (${target.architecture})`, data: target.exe }))} selectedOption={exe} onChange={(option) => setExe(String(option.data))}>Game executable</DropdownItem></PanelSectionRow>
    <PanelSectionRow><ButtonItem onClick={() => void refresh()}>Refresh library</ButtonItem></PanelSectionRow>
    {status.installed ? <>
      <PanelSectionRow><Field>Managed target: {status.manifest?.directory}{status.integrity === false ? " — files changed outside this plugin" : ""}</Field></PanelSectionRow>
      <PanelSectionRow><DropdownItem rgOptions={[{ label: "100% · best quality", data: "1" }, { label: "75% · quality", data: "0.75" }, { label: "50% · balanced", data: "0.5" }, { label: "25% · fastest", data: "0.25" }]} selectedOption={settings.WorkingScale || "1"} onChange={(option) => void update({ WorkingScale: String(option.data) })}>Model resolution</DropdownItem></PanelSectionRow>
      <PanelSectionRow><DropdownItem rgOptions={[{ label: "1 · recommended", data: "1" }, { label: "2 · much slower", data: "2" }]} selectedOption={settings.Passes || "1"} onChange={(option) => void update({ Passes: String(option.data) })}>Model passes</DropdownItem></PanelSectionRow>
      <PanelSectionRow><ToggleField checked={settings.Enabled === "1"} onChange={(value: boolean) => void update({ Enabled: value ? "1" : "0" })}>Enable preprocess</ToggleField></PanelSectionRow>
      <PanelSectionRow><DropdownItem rgOptions={["off", "auto", "fixed"].map((value) => ({ label: value, data: value }))} selectedOption={settings.Exposure || "off"} onChange={(option) => void update({ Exposure: String(option.data) })}>Exposure</DropdownItem></PanelSectionRow>
      <PanelSectionRow><SliderField label="Exposure bias" value={Number(settings.ExposureBias || "0")} min={-8} max={8} step={0.1} showValue editableValue valueSuffix=" EV" onChange={(value) => void update({ ExposureBias: String(value) })} /></PanelSectionRow>
      <PanelSectionRow><DropdownItem rgOptions={["none", "neutral", "reinhard", "filmic", "gt", "aces", "agx"].map((value) => ({ label: value, data: value }))} selectedOption={settings.Curve || "none"} onChange={(option) => void update({ Curve: String(option.data) })}>Display curve</DropdownItem></PanelSectionRow>
      <PanelSectionRow><SliderField label="Contrast" value={Number(settings.Contrast || "1")} min={0.5} max={2} step={0.01} showValue editableValue onChange={(value) => void update({ Contrast: String(value) })} /></PanelSectionRow>
      <PanelSectionRow><SliderField label="Saturation" value={Number(settings.Saturation || "1")} min={0.05} max={2} step={0.01} showValue editableValue onChange={(value) => void update({ Saturation: String(value) })} /></PanelSectionRow>
      <PanelSectionRow><ToggleField checked={settings.Sound !== "0"} onChange={(value: boolean) => void update({ Sound: value ? "1" : "0" })}>Toggle sound</ToggleField></PanelSectionRow>
      <PanelSectionRow><ButtonItem onClick={() => void uninstall()}>Remove from this game</ButtonItem></PanelSectionRow>
    </> : <>
      <PanelSectionRow><Field>⚠️ Do not use with online, competitive, or anti-cheat protected games. Close the game before installing.</Field></PanelSectionRow>
      <PanelSectionRow><Field>DLSS 5 model source: choose your own local NVIDIA DLL/zip. This plugin never ships, downloads, uploads, or retains NVIDIA model files.</Field></PanelSectionRow>
      <PanelSectionRow><input value={model} onChange={(event) => setModel(event.target.value)} placeholder="/home/deck/Downloads/nvngx_dlssnr.dll" style={{ width: "100%" }} /></PanelSectionRow>
      <PanelSectionRow><ToggleField checked={antiCheatAcknowledged} onChange={setAntiCheatAcknowledged}>I confirm this is offline and has no anti-cheat</ToggleField></PanelSectionRow>
      <PanelSectionRow><ToggleField checked={replace} onChange={setReplace}>Back up and replace colliding injection files</ToggleField></PanelSectionRow>
      <PanelSectionRow><ButtonItem onClick={() => void apply()}>Install into selected game</ButtonItem></PanelSectionRow>
    </>}
  </PanelSection>;
}

export default definePlugin(() => ({ name: "DLSSNR Manager", titleView: <div className={staticClasses.Title}>DLSSNR Manager</div>, content: <Content />, icon: <FaWandMagicSparkles /> }));
