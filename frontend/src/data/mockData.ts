import { Incident, RoboticsPackage, SimRobotState } from '../types';

export const MOCK_INCIDENTS: Incident[] = [
  {
    id: 'INC-2026-894',
    title: 'DB Connection Pool Exhaustion on High-Load Telemetry Spike',
    service: 'ops-sentinel-core / db-pool',
    rootCause: 'Database connection retry logic bug. Generated fix adds robust error handling and exponential backoff.',
    timestamp: '2 mins ago',
    status: 'pending_review',
    filePath: 'src/backend/db/pool_manager.py',
    tokenCount: 1300,
    processingTime: '3.0s',
    riskScore: 'Low (Passed)',
    riskLevel: 'Low',
    baseCode: `class DatabasePoolManager:
    def __init__(self, dsn: str, max_connections: int = 20):
        self.dsn = dsn
        self.max_connections = max_connections
        self.pool = None

    async def get_connection(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(self.dsn)
        return await self.pool.acquire()

    async def execute_query(self, query: str, *args):
        conn = await self.get_connection()
        try:
            return await conn.fetch(query, *args)
        finally:
            await self.pool.release(conn)`,
    proposedCode: `class DatabasePoolManager:
    def __init__(self, dsn: str, max_connections: int = 20):
        self.dsn = dsn
        self.max_connections = max_connections
        self.pool = None
        self._lock = asyncio.Lock()

    async def get_connection(self):
        async with self._lock:
            if not self.pool:
                for attempt in range(5):
                    try:
                        self.pool = await asyncpg.create_pool(
                            self.dsn,
                            max_size=self.max_connections,
                            timeout=5.0
                        )
                        break
                    except Exception as exc:
                        await asyncio.sleep(0.5 * (2 ** attempt))
                else:
                    raise ConnectionError("Failed to initialize database pool after 5 retries.")
        return await self.pool.acquire()

    async def execute_query(self, query: str, *args):
        conn = await self.get_connection()
        try:
            return await conn.fetch(query, *args)
        except asyncpg.PostgresError as e:
            logger.error(f"Query execution failed: {e}")
            raise
        finally:
            await self.pool.release(conn)`,
    steps: [
      { id: 1, label: 'Incident Detected', status: 'completed', timestamp: '14:02:11', detail: 'High latency threshold breached (>1200ms)' },
      { id: 2, label: 'Log Analysis', status: 'completed', timestamp: '14:02:13', detail: 'Identified 45 unreleased asyncpg socket connections' },
      { id: 3, label: 'Codebase RAG Query', status: 'completed', timestamp: '14:02:14', detail: 'Retrieved pool_manager.py and retry design guidelines' },
      { id: 4, label: 'Fix Generation', status: 'completed', timestamp: '14:02:16', detail: 'Generated exponential backoff & thread-safe lock' },
      { id: 5, label: 'Security Scan', status: 'completed', timestamp: '14:02:18', detail: 'SAST & SQL injection check passed (0 vulnerabilities)' },
      { id: 6, label: 'Human Approval', status: 'running', detail: 'Waiting for HITL SRE review & sign-off' },
    ]
  },
  {
    id: 'INC-2026-895',
    title: 'Inspire Hand RS485 Bus CRC Packet Drop Overflow',
    service: 'roboweaver-dexterous / rs485-driver',
    rootCause: 'Missing serial buffer purge before transmitting 6-DOF servo position commands.',
    timestamp: '14 mins ago',
    status: 'pending_review',
    filePath: 'src/roboweaver/hardware/inspire_hand_rs485.py',
    tokenCount: 840,
    processingTime: '1.8s',
    riskScore: 'Low (Passed)',
    riskLevel: 'Low',
    baseCode: `def send_position_command(self, finger_ids: List[int], angles: List[int]):
    frame = self.build_modbus_frame(finger_ids, angles)
    self.serial_port.write(frame)
    response = self.serial_port.read(12)
    return self.verify_crc(response)`,
    proposedCode: `def send_position_command(self, finger_ids: List[int], angles: List[int]):
    self.serial_port.reset_input_buffer()
    self.serial_port.reset_output_buffer()
    frame = self.build_modbus_frame(finger_ids, angles)
    self.serial_port.write(frame)
    self.serial_port.flush()
    response = self.serial_port.read(12)
    if not response or len(response) < 12:
        raise SerialTimeoutError("Inspire Hand RS485 frame ACK timeout")
    return self.verify_crc(response)`,
    steps: [
      { id: 1, label: 'Incident Detected', status: 'completed', timestamp: '13:48:02', detail: 'RS485 bus CRC error rate exceeded 4.2%' },
      { id: 2, label: 'Log Analysis', status: 'completed', timestamp: '13:48:03', detail: 'Serial RX buffer overflow on Modbus ID 0x01' },
      { id: 3, label: 'Codebase RAG Query', status: 'completed', timestamp: '13:48:05', detail: 'Retrieved inspire_hand_rs485.py & protocol manual' },
      { id: 4, label: 'Fix Generation', status: 'completed', timestamp: '13:48:07', detail: 'Added hardware RX/TX purge and timeout validation' },
      { id: 5, label: 'Security Scan', status: 'completed', timestamp: '13:48:08', detail: 'No privilege escalation or buffer injection detected' },
      { id: 6, label: 'Human Approval', status: 'running', detail: 'Awaiting Robotics On-Call sign-off' },
    ]
  },
  {
    id: 'INC-2026-890',
    title: 'TurtleBot4 Card Scanner Odom Drift Correction',
    service: 'card_scanner_ws / odom_ekf',
    rootCause: 'IMU covariance threshold too aggressive during rapid spin scanning turns.',
    timestamp: '41 mins ago',
    status: 'approved',
    filePath: 'src/card_scanner/config/ekf_filter.yaml',
    tokenCount: 512,
    processingTime: '1.2s',
    riskScore: 'Low (Passed)',
    riskLevel: 'Low',
    baseCode: `imu0_config: [false, false, false,
              true,  true,  true,
              true,  true,  true,
              false, false, false]
imu0_differential: true
imu0_relative: false`,
    proposedCode: `imu0_config: [false, false, false,
              true,  true,  true,
              true,  true,  true,
              false, false, false]
imu0_differential: false
imu0_relative: true
imu0_remove_gravitational_acceleration: true`,
    steps: [
      { id: 1, label: 'Incident Detected', status: 'completed', timestamp: '13:21:00' },
      { id: 2, label: 'Log Analysis', status: 'completed', timestamp: '13:21:01' },
      { id: 3, label: 'Codebase RAG Query', status: 'completed', timestamp: '13:21:02' },
      { id: 4, label: 'Fix Generation', status: 'completed', timestamp: '13:21:03' },
      { id: 5, label: 'Security Scan', status: 'completed', timestamp: '13:21:04' },
      { id: 6, label: 'Human Approval', status: 'approved', detail: 'Approved by Siddharth Patni (Lead SRE)' },
    ]
  }
];

export const MOCK_ROBOTICS_PACKAGES: RoboticsPackage[] = [
  {
    id: 'pkg-inspire-hand',
    name: 'inspire_hand_ros2',
    repo: 'github.com/Siddharthpatni/inspire_hand_ros2',
    category: 'Hardware Driver',
    rosDistro: 'ROS 2 Humble / Jazzy',
    description: 'Hardware driver for Inspire Robots Dexterous Hand RH56F1-E2 via RS485 Modbus protocol with tactile feedback.',
    topics: ['/inspire_hand/joint_states', '/inspire_hand/force_feedback', '/inspire_hand/cmd_grasp'],
    dependencies: ['rclcpp', 'sensor_msgs', 'modbus_serial', 'std_msgs'],
    status: 'Ready',
    stars: 124
  },
  {
    id: 'pkg-shopmate-r',
    name: 'shopmate_r_fleet',
    repo: 'github.com/Siddharthpatni/ShopMate-R',
    category: 'Fleet Control',
    rosDistro: 'ROS 2 Humble',
    description: 'Multi-robot orchestration framework connecting 3 autonomous retail robots with natural language prompt-to-task programming.',
    topics: ['/shopmate/fleet_status', '/shopmate/task_dispatcher', '/shopmate/collision_alert'],
    dependencies: ['nav2_msgs', 'geometry_msgs', 'action_msgs', 'roboweaver_core'],
    status: 'Active',
    stars: 218
  },
  {
    id: 'pkg-card-scanner',
    name: 'card_scanner_ws',
    repo: 'github.com/yashchothani/card_scannner_ws',
    category: 'Perception',
    rosDistro: 'ROS 2 Humble',
    description: 'TurtleBot4 autonomous navigation & computer vision package for precision card scanning in structured environments.',
    topics: ['/card_scanner/scan_result', '/card_scanner/target_pose', '/odom'],
    dependencies: ['cv_bridge', 'image_transport', 'turtlebot4_navigation', 'tf2_ros'],
    status: 'Ready',
    stars: 87
  },
  {
    id: 'pkg-kalachakra',
    name: 'kalachakra_core',
    repo: 'github.com/Siddharthpatni/kalachakra-framework',
    category: 'Navigation',
    rosDistro: 'ROS 2 Jazzy',
    description: 'Temporal-spatial path planning framework for dynamic obstacle avoidance and multi-robot scheduling.',
    topics: ['/kalachakra/time_horizon', '/kalachakra/trajectory_opt', '/tf'],
    dependencies: ['nav2_core', 'eigen3_cmake_module', 'visualization_msgs'],
    status: 'Optimizing',
    stars: 340
  },
  {
    id: 'pkg-nav2-bringup',
    name: 'nav2_bringup',
    repo: 'ros-planning/navigation2',
    category: 'Navigation',
    rosDistro: 'ROS 2 Humble / Jazzy',
    description: 'Production-grade ROS 2 Navigation stack for mobile robots with AMCL localization and costmap 2D.',
    topics: ['/map', '/amcl_pose', '/plan', '/cmd_vel'],
    dependencies: ['nav2_bt_navigator', 'nav2_costmap_2d', 'nav2_controller'],
    status: 'Ready',
    stars: 1840
  },
  {
    id: 'pkg-moveit2-servo',
    name: 'moveit2_servo',
    repo: 'ros-planning/moveit2',
    category: 'Manipulation',
    rosDistro: 'ROS 2 Jazzy',
    description: 'Real-time joint velocity servoing for high-DOF robotic arms and dexterous end-effectors.',
    topics: ['/servo_node/delta_twist_cmds', '/joint_states', '/collision_object'],
    dependencies: ['moveit_ros_planning', 'control_msgs', 'tf2_geometry_msgs'],
    status: 'Ready',
    stars: 950
  }
];

export const INITIAL_SIM_ROBOT: SimRobotState = {
  id: 'ROB-RH56F1-E2',
  name: 'Inspire Dexterous Hand RH56F1-E2',
  model: 'RH56F1-E2 (6-DOF RS485 Modbus)',
  bus: '/dev/ttyUSB0 @ 115200 baud',
  protocol: 'RS485 CRC-16 Modbus RTU',
  graspState: 'Precision Grip',
  slipRiskPercentage: 14.2,
  temperature: 36.4,
  voltage: 24.1,
  fingers: [
    { name: 'Thumb (Rot)', angleDeg: 42, forceN: 18.5, targetN: 20.0, contact: true },
    { name: 'Thumb (Flex)', angleDeg: 55, forceN: 22.1, targetN: 22.0, contact: true },
    { name: 'Index Finger', angleDeg: 68, forceN: 24.0, targetN: 25.0, contact: true },
    { name: 'Middle Finger', angleDeg: 65, forceN: 21.8, targetN: 22.0, contact: true },
    { name: 'Ring Finger', angleDeg: 30, forceN: 4.2, targetN: 5.0, contact: false },
    { name: 'Little Finger', angleDeg: 28, forceN: 2.1, targetN: 2.0, contact: false },
  ],
  jointAngles: [42, 55, 68, 65, 30, 28]
};
