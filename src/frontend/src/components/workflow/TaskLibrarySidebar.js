import React, { useMemo } from 'react';
import { Card, Alert } from 'react-bootstrap';
import { TASK_TYPES, TASK_CATEGORIES, DATA_TYPE_COLORS } from './constants';

const TaskLibrarySidebar = ({ setDraggedTaskType }) => {
  const tasksByCategory = useMemo(() => {
    const grouped = {};
    Object.entries(TASK_TYPES).forEach(([key, taskType]) => {
      const category = taskType.category || 'Other';
      if (!grouped[category]) {
        grouped[category] = [];
      }
      grouped[category].push({ key, ...taskType });
    });
    return grouped;
  }, []);

  return (
    <div className="task-library-sidebar" style={{ 
      width: '400px', 
      transition: 'width 0.3s ease',
      overflowY: 'auto',
      overflowX: 'hidden',
      flexShrink: 0
    }}>
      <div className="p-3">
        <div className="d-flex justify-content-between align-items-center mb-3">
          <h6 className="mb-0">Task Library</h6>
        </div>
        
        <Alert variant="info" className="mb-3">
          <small>
            <strong>How to use:</strong><br/>
            • Drag tasks into step areas on the canvas<br/>
            • Tasks automatically snap to the correct step<br/>
            • Use step panel on left to add/rename/remove steps<br/>
            • Connect output handles (right) to input handles (left)<br/>
            • Use ⚙️ to configure, 🗑️ to delete tasks<br/>
            • <strong>Tip:</strong> Steps execute sequentially, tasks within steps run in parallel
          </small>
        </Alert>

        <div className="task-library-legend mb-3">
          <h6 className="mb-2">Output types</h6>
          <div className="d-flex flex-wrap gap-2">
            {Object.entries(DATA_TYPE_COLORS)
              .filter(([key]) => key !== 'default')
              .map(([type, color]) => (
                <span
                  key={type}
                  className="d-inline-flex align-items-center gap-1"
                  style={{ fontSize: '11px' }}
                  title={type}
                >
                  <span
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: '50%',
                      backgroundColor: color,
                      border: `1px solid ${color}`,
                      flexShrink: 0,
                    }}
                  />
                  <span className="text-muted">{type}</span>
                </span>
              ))}
          </div>
        </div>

        {/* Task Categories */}
        {Object.entries(tasksByCategory).map(([category, tasks]) => {
          const categoryInfo = TASK_CATEGORIES[category] || { color: '#666', icon: '⚙️' };
          
          return (
            <div key={category} className="mb-4">
              <h6 style={{ color: categoryInfo.color }}>
                {categoryInfo.icon} {category}
              </h6>
              <div className="d-grid gap-2">
                {tasks.map((task) => (
                  <Card
                    key={task.key}
                    draggable
                    onDragStart={(e) => {
                      setDraggedTaskType(task.key);
                      e.dataTransfer.effectAllowed = 'move';
                    }}
                    style={{ 
                      cursor: 'grab',
                      borderColor: categoryInfo.color,
                      borderWidth: '2px'
                    }}
                    className="task-card"
                  >
                    <Card.Body className="p-2">
                      <div className="d-flex align-items-center">
                        <span className="me-2" style={{ fontSize: '16px' }}>
                          {task.icon}
                        </span>
                        <div className="flex-grow-1">
                          <div className="fw-bold" style={{ fontSize: '14px' }}>
                            {task.name}
                          </div>
                          <small className="text-muted">
                            {task.description}
                          </small>
                        </div>
                      </div>
                    </Card.Body>
                  </Card>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default TaskLibrarySidebar;