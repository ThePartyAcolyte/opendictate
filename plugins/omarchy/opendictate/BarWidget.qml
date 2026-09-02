import QtQuick
import QtQuick.Layouts
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "I18n.js" as I18n

Panel {
  id: root
  moduleName: "com.kirulab.opendictate"
  ipcTarget: "opendictate"
  manageIpc: false

  property var stateData: null
  property var levelHistory: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
  property real pulsePosition: 0.0
  property int pulseDirection: 1

  readonly property bool vertical: bar ? bar.vertical : false
  readonly property int barSize: (bar && bar.barSize) ? bar.barSize : Style.bar.sizeHorizontal
  readonly property string daemonState: stateData ? (stateData.state || "IDLE") : "OFFLINE"
  readonly property bool isRecording: daemonState === "RECORDING"
  readonly property bool isPaused: daemonState === "PAUSED"
  readonly property bool isBusy: daemonState === "TRANSCRIBING" || daemonState === "CLEANING" || daemonState === "PROCESSING" || daemonState === "LOADING"
  readonly property bool isOffline: daemonState === "OFFLINE" || !stateData
  readonly property bool isExtended: isRecording || isPaused || isBusy
  readonly property real audioLevel: stateData && stateData.level !== undefined ? Number(stateData.level) : 0.0
  readonly property string timeStr: stateData && stateData.time_str ? String(stateData.time_str) : "00:00"
  readonly property string sttBackend: cfgValue("stt_backend", "local_whisper")
  readonly property string modelSize: cfgValue("whisper_model_size", "medium")
  readonly property bool aiEnabled: cfgBool("ai_enabled", false)
  readonly property bool autosendEnabled: cfgBool("auto_send", false)
  readonly property bool realtimeEnabled: cfgBool("realtime_mode", true)
  readonly property bool pauseMedia: cfgBool("auto_pause_media", true)
  readonly property string currentLang: cfgValue("ui_language", "es")
  readonly property string statusText: stateData && stateData.status_text ? stateData.status_text : (isOffline ? t("status_offline") : t("status_ready"))

  readonly property var reservedSession: stateData && stateData.reserved_session ? stateData.reserved_session : null
  readonly property bool isReserved: !!reservedSession
  readonly property string reservedAppName: isReserved ? (reservedSession.app_name || "App") : ""
  readonly property color reservedAccentColor: (isReserved && reservedSession.accent_color) ? reservedSession.accent_color : Color.accent

  function t(key, fallback) {
    return I18n.get(currentLang, key, fallback)
  }

  readonly property color stateAccentColor: {
    if (isPaused) return Color.urgent
    if (isReserved) return reservedAccentColor
    if (sttBackend === "gemini_live") return "#5c8fff"
    return Color.accent
  }

  function cfgValue(key, fallback) {
    if (stateData && stateData.config && stateData.config[key] !== undefined && stateData.config[key] !== null) {
      return stateData.config[key]
    }
    if (stateData && stateData[key] !== undefined && stateData[key] !== null) {
      return stateData[key]
    }
    return fallback
  }

  function cfgBool(key, fallback) {
    var val = cfgValue(key, fallback)
    return val === true || val === "true" || val === 1
  }

  function parseState(content) {
    try {
      var parsed = JSON.parse(String(content || "{}"))
      if (parsed && typeof parsed === "object") {
        root.stateData = parsed
        if (parsed.level !== undefined) {
          addAudioSample(Number(parsed.level))
        }
      }
    } catch (e) {}
  }

  function addAudioSample(val) {
    var copy = levelHistory.slice(1)
    copy.push(Math.max(0.05, Math.min(1.0, val)))
    levelHistory = copy
    if (waveformCanvas.visible) waveformCanvas.requestPaint()
  }

  function sendCommand(cmd) {
    Quickshell.execDetached(["opendictate", "--" + cmd])
  }

  function updateConfig(key, val) {
    Quickshell.execDetached(["opendictate", "--set-config", String(key), String(val)])
    if (!root.stateData) root.stateData = {}
    if (!root.stateData.config) root.stateData.config = {}
    root.stateData.config[key] = val
    root.stateData[key] = val
  }

  function toggleConfig(key) {
    var curr = cfgBool(key, false)
    updateConfig(key, !curr)
  }

  function ensureDaemonRunning() {
    Quickshell.execDetached(["opendictate", "--record"])
  }

  FileView {
    id: stateWatcher
    path: "/tmp/opendictate_state.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.parseState(text())
    onLoadFailed: root.stateData = null
  }

  Timer {
    id: statePollingTimer
    interval: 300
    running: true
    repeat: true
    onTriggered: stateWatcher.reload()
  }

  Timer {
    id: audioSampleTimer
    interval: 60
    running: root.isRecording
    repeat: true
    onTriggered: {
      if (root.audioLevel > 0) {
        root.addAudioSample(root.audioLevel)
      } else {
        var noise = 0.05 + Math.random() * 0.12
        root.addAudioSample(noise)
      }
    }
  }

  Timer {
    id: pulseTimer
    interval: 30
    running: root.isBusy
    repeat: true
    onTriggered: {
      root.pulsePosition += 0.04 * root.pulseDirection
      if (root.pulsePosition >= 1.0) {
        root.pulsePosition = 1.0
        root.pulseDirection = -1
      } else if (root.pulsePosition <= 0.0) {
        root.pulsePosition = 0.0
        root.pulseDirection = 1
      }
      if (waveformCanvas.visible) waveformCanvas.requestPaint()
    }
  }

  // Centered Floating Settings Window Modal
  SettingsDialog {
    id: settingsDialog
    stateData: root.stateData
  }

  IpcHandler {
    target: "opendictate"
    function open() { root.open() }
    function close() { root.close() }
    function show() { root.open() }
    function hide() { root.close() }
    function toggle() { root.toggle() }
    function openSettings() { root.close(); settingsDialog.open = true }
    function settings() { root.close(); settingsDialog.open = true }
  }

  // --- Dynamic Bar Geometry ---
  implicitWidth: isExtended ? (extendedRow.implicitWidth + Style.space(16)) : root.barSize
  implicitHeight: root.barSize

  Behavior on implicitWidth {
    NumberAnimation { duration: 200; easing.type: Easing.OutCubic }
  }

  // --- Background Pill Container for Extended State ---
  Rectangle {
    id: barPill
    anchors.fill: parent
    anchors.margins: Style.space(2)
    radius: Style.cornerRadius > 0 ? Style.cornerRadius : (height / 2)
    color: root.isExtended ? Qt.rgba(Color.foreground.r, Color.foreground.g, Color.foreground.b, 0.08) : "transparent"
    border.color: root.isExtended ? (root.isPaused ? Color.urgent : (root.sttBackend === "gemini_live" ? "#5c8fff" : Color.accent)) : "transparent"
    border.width: root.isExtended ? 1 : 0
    visible: root.isExtended
  }

  // =========================================================================
  // COMPACT MODE: Single Bar Icon Button
  // =========================================================================
  Item {
    id: compactButton
    anchors.fill: parent
    visible: !root.isExtended

    BarIconButton {
      id: iconBtn
      anchors.fill: parent
      bar: root.bar
      text: root.isOffline ? "󰍭" : "󰍬"
      foreground: root.isOffline ? Color.muted : (root.isReserved ? root.reservedAccentColor : (root.sttBackend === "gemini_live" ? "#5c8fff" : Color.accent))
      tooltipText: root.isOffline 
        ? ("OpenDictate (" + root.t("status_offline") + ")")
        : (root.isReserved 
            ? ("OpenDictate — " + root.t("lbl_reserved_for", "Reservado para") + " " + root.reservedAppName)
            : ("OpenDictate (" + (root.sttBackend === "gemini_live" ? "Gemini Live" : root.modelSize) + ")"))

      onPressed: function(b) {
        if (b === Qt.RightButton) {
          root.toggle()
        } else {
          if (root.isOffline) {
            root.ensureDaemonRunning()
          } else {
            root.sendCommand("record")
          }
        }
      }
    }
  }

  // =========================================================================
  // EXTENDED MODE: Full Recording, Sound Curve & Quick Actions in Bar
  // =========================================================================
  Row {
    id: extendedRow
    anchors.centerIn: parent
    visible: root.isExtended
    spacing: Style.space(6)

    // 1. Record / Pause Toggle Button
    Item {
      width: root.barSize - Style.space(4)
      height: root.barSize - Style.space(4)
      anchors.verticalCenter: parent.verticalCenter

      Text {
        id: statusIconText
        anchors.centerIn: parent
        text: root.isPaused ? "󰐊" : (root.isBusy ? "󰑐" : "󰏤")
        font.family: Style.font.family
        font.pixelSize: Style.bar.iconFont
        color: root.stateAccentColor
        rotation: 0

        RotationAnimation on rotation {
          running: root.isBusy
          loops: Animation.Infinite
          from: 0
          to: 360
          duration: 1000
        }

        Connections {
          target: root
          function onIsBusyChanged() {
            if (!root.isBusy) statusIconText.rotation = 0
          }
        }
      }

      MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: {
          if (root.isRecording) root.sendCommand("pause")
          else if (root.isPaused) root.sendCommand("record")
        }
      }
    }

    // 2. Sound Curve / Waveform Canvas
    Canvas {
      id: waveformCanvas
      width: Style.space(80)
      height: root.barSize - Style.space(12)
      anchors.verticalCenter: parent.verticalCenter

      onPaint: {
        var ctx = getContext("2d")
        ctx.clearRect(0, 0, width, height)

        if (root.isBusy) {
          // Indeterminate pulse line
          var pulseWidth = width * 0.4
          var startX = (width - pulseWidth) * root.pulsePosition

          ctx.strokeStyle = Qt.rgba(1.0, 1.0, 1.0, 0.2)
          ctx.lineWidth = 2.0
          ctx.beginPath()
          ctx.moveTo(0, height / 2)
          ctx.lineTo(width, height / 2)
          ctx.stroke()

          ctx.strokeStyle = root.sttBackend === "gemini_live" ? "#5c8fff" : Color.accent
          ctx.lineWidth = 3.0
          ctx.beginPath()
          ctx.moveTo(startX, height / 2)
          ctx.lineTo(startX + pulseWidth, height / 2)
          ctx.stroke()
          return
        }

        // Live Dynamic Sound Waveform Bars
        var count = root.levelHistory.length
        var barWidth = Math.max(2, (width / count) - 1.5)
        var maxH = height - 2

        ctx.fillStyle = root.isPaused 
          ? Color.urgent 
          : (root.sttBackend === "gemini_live" ? "#5c8fff" : Color.accent)

        for (var i = 0; i < count; i++) {
          var val = root.levelHistory[i] || 0.05
          var h = Math.max(3, val * maxH)
          var x = i * (width / count)
          var y = (height - h) / 2
          ctx.fillRect(x, y, barWidth, h)
        }
      }
    }

    // 3. Elapsed Time Indicator
    Text {
      anchors.verticalCenter: parent.verticalCenter
      text: root.timeStr
      font.family: Style.font.family
      font.pixelSize: Style.font.caption
      font.bold: true
      color: Color.foreground
    }

    // 4. Send / Finish Dictation Button
    Item {
      width: root.barSize - Style.space(6)
      height: root.barSize - Style.space(6)
      anchors.verticalCenter: parent.verticalCenter

      Text {
        anchors.centerIn: parent
        text: "󰒭"
        font.family: Style.font.family
        font.pixelSize: Style.font.body
        color: "#10B981"
      }

      MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.sendCommand("send")
      }
    }

    // 5. Cancel / Discard Dictation Button
    Item {
      width: root.barSize - Style.space(6)
      height: root.barSize - Style.space(6)
      anchors.verticalCenter: parent.verticalCenter

      Text {
        anchors.centerIn: parent
        text: "󰜺"
        font.family: Style.font.family
        font.pixelSize: Style.font.body
        color: Color.urgent
      }

      MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.sendCommand("cancel")
      }
    }
  }

  // =========================================================================
  // POPUP PANEL: Clean Context & Quick Status in Bar
  // =========================================================================
  KeyboardPanel {
    id: panel
    anchorItem: root
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(340))
    contentHeight: panel.fittedContentHeight(popupColumn.implicitHeight + Style.space(24), Style.space(560))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()

      Column {
        id: popupColumn
        width: parent.width
        spacing: Style.space(8)

        // Header: Logo, Title and Active Status
        Row {
          width: parent.width
          spacing: Style.space(10)

          Text {
            anchors.verticalCenter: parent.verticalCenter
            text: "󰍬"
            color: root.stateAccentColor
            font.family: Style.font.family
            font.pixelSize: Style.font.title
          }

          Column {
            anchors.verticalCenter: parent.verticalCenter
            spacing: Style.space(2)

            Text {
              text: "OpenDictate"
              font.family: Style.font.family
              font.pixelSize: Style.font.body
              font.bold: true
              color: Color.foreground
            }

            Text {
              text: root.statusText
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
              color: root.isOffline ? Color.muted : (root.isPaused ? Color.urgent : Color.accent)
            }
          }
        }

        PanelSeparator { width: parent.width }

        // Quick Switches Section
        PanelSectionHeader {
          text: root.t("quick_settings")
        }

        Toggle {
          width: parent.width
          label: root.t("lbl_ai_enabled")
          description: root.t("desc_ai_enabled")
          checked: root.aiEnabled
          onClicked: root.sendCommand("toggle-ai")
        }

        Toggle {
          width: parent.width
          label: root.t("lbl_auto_send")
          description: root.t("desc_auto_send")
          checked: root.autosendEnabled
          onClicked: root.sendCommand("toggle-autosend")
        }

        Toggle {
          width: parent.width
          label: root.t("lbl_realtime_mode")
          description: root.t("desc_realtime_mode")
          checked: root.realtimeEnabled
          onClicked: root.sendCommand("toggle-realtime")
        }

        Toggle {
          width: parent.width
          label: root.t("lbl_auto_pause")
          description: root.t("desc_auto_pause")
          checked: root.pauseMedia
          onClicked: root.toggleConfig("auto_pause_media")
        }

        PanelSeparator { width: parent.width }

        // STT Engine Selector
        PanelSectionHeader {
          text: root.t("stt_engine")
        }

        Row {
          width: parent.width
          spacing: Style.space(8)

          Button {
            width: (parent.width - Style.space(8)) / 2
            text: "Local"
            selected: root.sttBackend !== "gemini_live"
            onClicked: root.updateConfig("stt_backend", "local_whisper")
          }

          Button {
            width: (parent.width - Style.space(8)) / 2
            text: "Gemini"
            selected: root.sttBackend === "gemini_live"
            onClicked: root.updateConfig("stt_backend", "gemini_live")
          }
        }

        PanelSeparator { width: parent.width }

        // Footer Actions: Settings & Quit
        Row {
          width: parent.width
          spacing: Style.space(8)

          Button {
            width: (parent.width - Style.space(8)) / 2
            text: root.t("btn_settings")
            onClicked: {
              root.close()
              settingsDialog.open = true
            }
          }

          Button {
            width: (parent.width - Style.space(8)) / 2
            text: root.t("btn_quit")
            foreground: Color.urgent
            onClicked: {
              root.close()
              root.sendCommand("quit")
            }
          }
        }
      }
    }
  }
}
