import QtQuick
import QtQuick.Window

Item {
    id: handles
    required property Window windowHost
    enabled: windowHost.visibility === Window.Windowed && !windowHost.geometryAnimating
    Repeater {
        model: [
            {edges: Qt.LeftEdge, cursor: Qt.SizeHorCursor}, {edges: Qt.RightEdge, cursor: Qt.SizeHorCursor},
            {edges: Qt.TopEdge, cursor: Qt.SizeVerCursor}, {edges: Qt.BottomEdge, cursor: Qt.SizeVerCursor},
            {edges: Qt.TopEdge | Qt.LeftEdge, cursor: Qt.SizeFDiagCursor}, {edges: Qt.BottomEdge | Qt.RightEdge, cursor: Qt.SizeFDiagCursor},
            {edges: Qt.TopEdge | Qt.RightEdge, cursor: Qt.SizeBDiagCursor}, {edges: Qt.BottomEdge | Qt.LeftEdge, cursor: Qt.SizeBDiagCursor}
        ]
        MouseArea {
            required property var modelData
            readonly property bool edgeLeft: (modelData.edges & Qt.LeftEdge) !== 0
            readonly property bool edgeRight: (modelData.edges & Qt.RightEdge) !== 0
            readonly property bool edgeTop: (modelData.edges & Qt.TopEdge) !== 0
            readonly property bool edgeBottom: (modelData.edges & Qt.BottomEdge) !== 0
            readonly property bool corner: (edgeLeft || edgeRight) && (edgeTop || edgeBottom)
            width: corner ? 10 : edgeLeft || edgeRight ? 6 : handles.width - 20
            height: corner ? 10 : edgeTop || edgeBottom ? 6 : handles.height - 20
            x: edgeLeft ? 0 : edgeRight ? handles.width - width : 10
            y: edgeTop ? 0 : edgeBottom ? handles.height - height : 10
            cursorShape: modelData.cursor
            onPressed: handles.windowHost.startSystemResize(modelData.edges)
        }
    }
}
